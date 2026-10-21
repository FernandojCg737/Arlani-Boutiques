import { HttpClient } from '@angular/common/http';
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

// CU08, pedido explicito del usuario: pantalla dividida -- sucursales a la
// izquierda, catalogo y disponibilidad de la elegida a la derecha. Antes se
// precargaban todas las sucursales apiladas verticalmente; ahora se carga
// (y cachea) el catalogo de una sucursal recien cuando se hace click en
// ella, mostrando solo esa a la vez.
@Component({
  selector: 'app-admin-catalogo',
  imports: [],
  templateUrl: './catalogo.html',
  styleUrl: './catalogo.scss',
})
export class AdminCatalogo implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);

  // CU08, mismo criterio que CU12: un Encargado/Cajero solo consulta el
  // catalogo de SU sucursal, nunca el de otras -- Administrador ve todas.
  protected readonly esAdministrador = computed(() => this.auth.isAdmin());

  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly sucursalSeleccionada = signal<Sucursal | null>(null);
  protected readonly productos = signal<ProductoCatalogo[]>([]);
  protected readonly loadingSucursales = signal(false);
  protected readonly loadingCatalogo = signal(false);
  protected readonly error = signal('');
  protected readonly errorCatalogo = signal('');
  protected readonly busqueda = signal('');

  // Cache por sucursal: volver a hacer click en una ya vista no vuelve a pedirla.
  private readonly cache = new Map<number, ProductoCatalogo[]>();

  protected readonly productosFiltrados = computed(() => {
    const termino = this.busqueda().trim().toLowerCase();
    const productos = this.productos();
    if (!termino) return productos;

    return productos.filter(
      (p) =>
        p.nombre.toLowerCase().includes(termino) ||
        p.marca_nombre.toLowerCase().includes(termino) ||
        p.categoria_nombre.toLowerCase().includes(termino) ||
        p.variantes.some(
          (v) => v.talla_codigo.toLowerCase().includes(termino) || v.color_nombre.toLowerCase().includes(termino),
        ),
    );
  });

  ngOnInit(): void {
    void this.loadSucursales();
  }

  protected async seleccionar(sucursal: Sucursal): Promise<void> {
    this.sucursalSeleccionada.set(sucursal);
    this.errorCatalogo.set('');
    this.busqueda.set('');

    const cacheado = this.cache.get(sucursal.id);
    if (cacheado) {
      this.productos.set(cacheado);
      return;
    }

    this.loadingCatalogo.set(true);
    this.productos.set([]);
    try {
      const productos = await firstValueFrom(
        this.http.get<ProductoCatalogo[]>(`${environment.apiUrl}/catalogo/sucursales/${sucursal.id}/productos`),
      );
      this.cache.set(sucursal.id, productos);
      this.productos.set(productos);
    } catch {
      this.errorCatalogo.set('No se pudo cargar el catalogo de esta sucursal.');
    } finally {
      this.loadingCatalogo.set(false);
    }
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
