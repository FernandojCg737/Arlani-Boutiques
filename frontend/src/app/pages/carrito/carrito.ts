import { DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { BOUTIQUES, Boutique } from '../../data/boutiques';
import { Auth } from '../../services/auth';
import { Cart, DetalleCarrito } from '../../services/cart';

interface GrupoBoutique {
  boutique: Boutique;
  items: DetalleCarrito[];
  subtotal: number;
}

interface Sucursal {
  id: number;
  nombre: string;
  direccion: string;
}

type EstadoReserva = 'formulario' | 'enviando' | 'listo' | 'error';

@Component({
  selector: 'app-carrito',
  imports: [RouterLink, DecimalPipe],
  templateUrl: './carrito.html',
  styleUrl: './carrito.scss',
})
export class Carrito implements OnInit {
  protected readonly cart = inject(Cart);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  protected readonly auth = inject(Auth);

  // Carrito de la plataforma: las prendas se agrupan por la boutique que las
  // vende. TODO: cuando el detalle del carrito traiga la empresa (módulo
  // multiempresa), agrupar por ese dato; hoy todas son de la única boutique.
  protected readonly grupos = computed<GrupoBoutique[]>(() => {
    const items = this.cart.items();
    if (items.length === 0) return [];
    return [{ boutique: BOUTIQUES[0], items, subtotal: items.reduce((suma, i) => suma + i.subtotal, 0) }];
  });

  // Reservar el carrito entero: en vez de pagar ahora, retiene el stock y le
  // adjunta la fecha/hora en que el cliente ira a la sucursal a pagar y
  // recoger -- reusa el mismo POST /reservas que ya usa CU10 desde la ficha
  // de producto, mandando todos los items del carrito de una.
  protected readonly reservaAbierta = signal(false);
  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly horario = signal('');
  protected readonly reservaEstado = signal<EstadoReserva>('formulario');
  protected readonly reservaError = signal('');

  protected readonly minDatetime = new Date(Date.now() + 60 * 60 * 1000).toISOString().slice(0, 16);

  ngOnInit(): void {
    if (this.auth.currentUser()) void this.cart.cargar();
  }

  protected decrease(id: number, currentQuantity: number): void {
    void this.cart.actualizarCantidad(id, currentQuantity - 1);
  }

  protected increase(id: number, currentQuantity: number): void {
    void this.cart.actualizarCantidad(id, currentQuantity + 1);
  }

  protected remove(id: number): void {
    void this.cart.eliminar(id);
  }

  protected irACheckout(): void {
    void this.router.navigate(['/checkout']);
  }

  protected async abrirReserva(): Promise<void> {
    this.reservaAbierta.set(true);
    this.reservaEstado.set('formulario');
    this.reservaError.set('');
    this.horario.set('');
    if (this.sucursales().length > 0) return;
    try {
      const res = await firstValueFrom(this.http.get<Sucursal[]>(`${environment.apiUrl}/sucursales/publico`));
      this.sucursales.set(res);
      this.sucursalId.set(res[0]?.id ?? null);
    } catch {
      this.reservaError.set('No pudimos cargar las sucursales.');
    }
  }

  protected cerrarReserva(): void {
    this.reservaAbierta.set(false);
  }

  protected async confirmarReserva(): Promise<void> {
    const sucursalId = this.sucursalId();
    if (!sucursalId || !this.horario()) return;

    this.reservaEstado.set('enviando');
    this.reservaError.set('');
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/reservas`, {
          sucursal_id: sucursalId,
          horario_atencion: new Date(this.horario()).toISOString(),
          items: this.cart.items().map((i) => ({
            producto_id: i.producto_id,
            talla_id: i.talla_id,
            color_id: i.color_id,
            cantidad: i.cantidad,
          })),
        }),
      );
      await this.cart.vaciar();
      this.reservaEstado.set('listo');
    } catch (err) {
      this.reservaError.set(this.extraerError(err));
      this.reservaEstado.set('formulario');
    }
  }

  private extraerError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'No se pudo crear la reserva.';
  }
}
