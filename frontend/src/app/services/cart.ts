import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

export interface DetalleCarrito {
  id: number;
  producto_id: number;
  producto_nombre: string;
  producto_imagen_url: string | null;
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  sucursal_id: number;
  sucursal_nombre: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
  // Boutique que vende la prenda (el carrito se agrupa por tienda).
  tienda?: string | null;
  tienda_nombre?: string | null;
  tienda_logo?: string | null;
  tienda_color?: string | null;
}

interface DetalleCarritoApi {
  id: number;
  producto_id: number;
  producto_nombre: string;
  producto_imagen_url: string | null;
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  sucursal_id: number;
  sucursal_nombre: string;
  cantidad: number;
  precio_unitario: string;
  subtotal: string;
  tienda?: string | null;
  tienda_nombre?: string | null;
  tienda_logo?: string | null;
  tienda_color?: string | null;
}

interface CarritoApi {
  id: number;
  estado: string;
  detalles: DetalleCarritoApi[];
  total: string;
}

// Pydantic serializa Decimal como texto (ej. "130.00"), no como numero JSON
// -- sin esto, sumar precios en el frontend hace concatenacion de strings
// en vez de una suma (0 + "320.00" da "0320.00", no 320).
function normalizarDetalle(d: DetalleCarritoApi): DetalleCarrito {
  return { ...d, precio_unitario: Number(d.precio_unitario), subtotal: Number(d.subtotal) };
}

// CU11: el carrito ahora persiste contra el backend (tabla Carrito /
// DetalleCarrito), asociado al cliente autenticado -- reemplaza la version
// anterior 100% local (localStorage). Por eso requiere sesion iniciada,
// igual que Reservas y el probador de RA. Quien lo usa (Header, la pagina
// de Carrito, Checkout) llama cargar() cuando corresponde; no se auto-carga
// solo al instanciarse para no disparar una llamada HTTP antes de saber si
// hay sesion.
@Injectable({ providedIn: 'root' })
export class Cart {
  private readonly http = inject(HttpClient);

  private readonly _items = signal<DetalleCarrito[]>([]);

  readonly items = this._items.asReadonly();
  readonly totalItems = computed(() => this._items().reduce((sum, i) => sum + i.cantidad, 0));
  readonly totalPrice = computed(() => this._items().reduce((sum, i) => sum + i.subtotal, 0));

  async cargar(): Promise<void> {
    try {
      const res = await firstValueFrom(this.http.get<CarritoApi>(`${environment.apiUrl}/carrito`));
      this._items.set(res.detalles.map(normalizarDetalle));
    } catch {
      // Sin sesion (401) u otro error de red: el carrito se ve vacio.
      this._items.set([]);
    }
  }

  limpiarLocal(): void {
    this._items.set([]);
  }

  async agregar(productoId: number, tallaId: number, colorId: number, sucursalId: number, cantidad: number): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<CarritoApi>(`${environment.apiUrl}/carrito/items`, {
        producto_id: productoId,
        talla_id: tallaId,
        color_id: colorId,
        sucursal_id: sucursalId,
        cantidad,
      }),
    );
    this._items.set(res.detalles.map(normalizarDetalle));
  }

  async actualizarCantidad(detalleId: number, cantidad: number): Promise<void> {
    if (cantidad < 1) {
      await this.eliminar(detalleId);
      return;
    }
    const res = await firstValueFrom(
      this.http.put<CarritoApi>(`${environment.apiUrl}/carrito/items/${detalleId}`, { cantidad }),
    );
    this._items.set(res.detalles.map(normalizarDetalle));
  }

  async eliminar(detalleId: number): Promise<void> {
    const res = await firstValueFrom(
      this.http.delete<CarritoApi>(`${environment.apiUrl}/carrito/items/${detalleId}`),
    );
    this._items.set(res.detalles.map(normalizarDetalle));
  }

  async vaciar(): Promise<void> {
    const res = await firstValueFrom(this.http.delete<CarritoApi>(`${environment.apiUrl}/carrito`));
    this._items.set(res.detalles.map(normalizarDetalle));
  }
}
