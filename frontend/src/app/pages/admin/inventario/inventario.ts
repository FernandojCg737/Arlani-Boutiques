import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';

interface Sucursal {
  id: number;
  nombre: string;
}

interface Variante {
  id: number;
  talla_codigo: string;
  color_nombre: string;
  cantidad: number;
}

interface ProductoCatalogo {
  id: number;
  nombre: string;
  marca_nombre: string;
  categoria_nombre: string;
  precio: string;
  imagen_url: string | null;
  cantidad_total: number;
  disponible: boolean;
  variantes: Variante[];
}

// CU12, pantalla dividida (mismo patron que CU08): sucursales a la
// izquierda, inventario editable de la elegida a la derecha. Un
// Encargado/Cajero solo ve SU sucursal (el backend tambien lo exige,
// rechaza el PUT si intenta tocar otra) -- Administrador ve/edita todas.
@Component({
  selector: 'app-admin-inventario',
  imports: [],
  templateUrl: './inventario.html',
  styleUrl: './inventario.scss',
})
export class AdminInventario implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);

  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly sucursalSeleccionada = signal<Sucursal | null>(null);
  protected readonly productos = signal<ProductoCatalogo[]>([]);
  protected readonly loadingSucursales = signal(false);
  protected readonly loadingInventario = signal(false);
  protected readonly error = signal('');
  protected readonly errorInventario = signal('');

  protected readonly esAdministrador = computed(() => this.auth.isAdmin());

  // Cache por sucursal: volver a hacer click en una ya vista no vuelve a pedirla.
  private readonly cache = new Map<number, ProductoCatalogo[]>();

  ngOnInit(): void {
    void this.loadSucursales();
  }

  protected async seleccionar(sucursal: Sucursal): Promise<void> {
    this.sucursalSeleccionada.set(sucursal);
    this.errorInventario.set('');

    const cacheado = this.cache.get(sucursal.id);
    if (cacheado) {
      this.productos.set(cacheado);
      return;
    }

    this.loadingInventario.set(true);
    this.productos.set([]);
    try {
      const productos = await firstValueFrom(
        this.http.get<ProductoCatalogo[]>(`${environment.apiUrl}/catalogo/sucursales/${sucursal.id}/productos`),
      );
      this.cache.set(sucursal.id, productos);
      this.productos.set(productos);
    } catch {
      this.errorInventario.set('No se pudo cargar el inventario de esta sucursal.');
    } finally {
      this.loadingInventario.set(false);
    }
  }

  protected async actualizarCantidad(producto: ProductoCatalogo, variante: Variante, valor: string): Promise<void> {
    const cantidad = Number(valor);
    if (Number.isNaN(cantidad) || cantidad < 0) return;

    try {
      const actualizada = await firstValueFrom(
        this.http.put<Variante>(`${environment.apiUrl}/productos/${producto.id}/inventario/${variante.id}`, {
          cantidad,
        }),
      );

      const aplicar = (productos: ProductoCatalogo[]): ProductoCatalogo[] =>
        productos.map((p) => {
          if (p.id !== producto.id) return p;
          const variantes = p.variantes.map((v) => (v.id === variante.id ? { ...v, cantidad: actualizada.cantidad } : v));
          const cantidad_total = variantes.reduce((sum, v) => sum + v.cantidad, 0);
          return { ...p, variantes, cantidad_total, disponible: cantidad_total > 0 };
        });

      this.productos.update(aplicar);
      const sucursal = this.sucursalSeleccionada();
      if (sucursal) {
        const cacheado = this.cache.get(sucursal.id);
        if (cacheado) this.cache.set(sucursal.id, aplicar(cacheado));
      }
    } catch (err) {
      this.errorInventario.set(this.extractError(err));
    }
  }

  private extractError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'Ocurrio un error inesperado.';
  }

  private async loadSucursales(): Promise<void> {
    this.error.set('');
    this.loadingSucursales.set(true);
    try {
      const res = await firstValueFrom(this.http.get<Sucursal[]>(`${environment.apiUrl}/catalogo/sucursales`));
      const propiaId = this.auth.currentUser()?.sucursal_id;
      const visibles = this.esAdministrador() ? res : res.filter((s) => s.id === propiaId);

      this.sucursales.set(visibles);
      if (visibles.length > 0) void this.seleccionar(visibles[0]);
    } catch {
      this.error.set('No se pudo cargar las sucursales.');
    } finally {
      this.loadingSucursales.set(false);
    }
  }
}
