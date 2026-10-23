import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Origen, SelectorOrigen } from '../../../components/selector-origen/selector-origen';

interface DetalleReservaItem {
  id: number;
  producto_id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad: number;
}

interface ReservaItem {
  id: number;
  cliente_id: number;
  cliente_nombre: string;
  cliente_email: string;
  sucursal_id: number;
  sucursal_nombre: string;
  horario_atencion: string;
  estado: string;
  fecha_creacion: string;
  detalles: DetalleReservaItem[];
}

interface ReservaPage {
  items: ReservaItem[];
  total: number;
  page: number;
  page_size: number;
}

interface Opcion {
  id: number;
  nombre: string;
}

@Component({
  selector: 'app-admin-reservas',
  imports: [DatePipe, SelectorOrigen],
  templateUrl: './reservas.html',
  styleUrl: './reservas.scss',
})
export class AdminReservas implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  // ONLINE / OFFLINE (las hechas sin conexion llegan al sincronizar, CU12):
  // solo si el plan de la tienda incluye la operacion sin conexion (Basico y
  // Profesional). Lo ve el personal (CU10) y el SuperAdministrador (CU05).
  protected readonly conOrigen = signal(false);
  protected readonly esPlataforma = this.route.snapshot.data['origenes'] === true;
  protected readonly planSinOffline = signal<string | null>(null);
  protected readonly origen = signal<Origen>(
    this.route.snapshot.queryParamMap.get('origen') === 'offline' ? 'offline' : 'online',
  );

  protected cambiarOrigen(o: Origen): void {
    if (o === this.origen()) return;
    this.origen.set(o);
    void this.router.navigate([], { queryParams: { origen: o }, queryParamsHandling: 'merge', replaceUrl: true });
    this.filtrar();
  }

  protected readonly items = signal<ReservaItem[]>([]);
  protected readonly sucursales = signal<Opcion[]>([]);
  protected readonly tallas = signal<Opcion[]>([]);
  protected readonly colores = signal<Opcion[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 20;
  protected readonly filtroEstado = signal('');
  protected readonly filtroSucursal = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly procesando = signal<number | null>(null);

  protected readonly editando = signal<ReservaItem | null>(null);
  protected readonly editSucursalId = signal<number | null>(null);
  protected readonly editTallaId = signal<number | null>(null);
  protected readonly editColorId = signal<number | null>(null);
  protected readonly editProductoId = signal<number | null>(null);
  protected readonly editCantidad = signal(1);
  protected readonly editHorario = signal('');
  protected readonly editError = signal('');
  protected readonly editGuardando = signal(false);

  protected get totalPages(): number {
    return Math.max(1, Math.ceil(this.total() / this.pageSize));
  }

  ngOnInit(): void {
    this.cargarCatalogo();
    void this.iniciar();
  }

  private async iniciar(): Promise<void> {
    try {
      const r = await firstValueFrom(
        this.http.get<{ offline: boolean; plan: string | null }>(`${environment.apiUrl}/ventas/origenes`),
      );
      this.conOrigen.set(r.offline);
      this.planSinOffline.set(r.offline ? null : r.plan);
    } catch {
      this.conOrigen.set(false);
    }
    if (!this.conOrigen() && this.origen() === 'offline') this.origen.set('online');
    await this.load();
  }

  protected filtrar(): void {
    this.page.set(1);
    this.load();
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.totalPages) return;
    this.page.set(page);
    this.load();
  }

  private async cargarCatalogo(): Promise<void> {
    try {
      const res = await firstValueFrom(
        this.http.get<{ sucursales: Opcion[]; tallas: Opcion[]; colores: Opcion[] }>(
          `${environment.apiUrl}/productos/catalogo-base`,
        ),
      );
      this.sucursales.set(res.sucursales);
      this.tallas.set(res.tallas);
      this.colores.set(res.colores);
    } catch {
      this.sucursales.set([]);
      this.tallas.set([]);
      this.colores.set([]);
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = {
        page: String(this.page()),
        page_size: String(this.pageSize),
      };
      if (this.filtroEstado()) params['estado'] = this.filtroEstado();
      if (this.filtroSucursal()) params['sucursal_id'] = this.filtroSucursal();
      if (this.conOrigen()) params['origen'] = this.origen();

      const res = await firstValueFrom(this.http.get<ReservaPage>(`${environment.apiUrl}/reservas`, { params }));
      this.items.set(res.items);
      this.total.set(res.total);
    } catch {
      this.error.set('No se pudo cargar las reservas.');
    } finally {
      this.loading.set(false);
    }
  }

  protected async confirmar(reserva: ReservaItem): Promise<void> {
    await this.cambiarEstado(reserva, 'confirmada');
  }

  protected async cancelar(reserva: ReservaItem): Promise<void> {
    if (!confirm(`Cancelar la reserva #${reserva.id} de ${reserva.cliente_nombre}?`)) return;
    await this.cambiarEstado(reserva, 'cancelada');
  }

  private async cambiarEstado(reserva: ReservaItem, estado: string): Promise<void> {
    this.procesando.set(reserva.id);
    this.error.set('');
    try {
      await firstValueFrom(
        this.http.put(`${environment.apiUrl}/reservas/${reserva.id}/estado`, { estado }),
      );
      await this.load();
    } catch {
      this.error.set('No se pudo actualizar la reserva.');
    } finally {
      this.procesando.set(null);
    }
  }

  protected async completar(reserva: ReservaItem): Promise<void> {
    if (!confirm(`Marcar la reserva #${reserva.id} como entregada? Esto descuenta el stock reservado.`)) return;
    this.procesando.set(reserva.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/reservas/${reserva.id}/completar`, {}));
      await this.load();
    } catch {
      this.error.set('No se pudo completar la reserva (revisa que haya stock suficiente).');
    } finally {
      this.procesando.set(null);
    }
  }

  protected async eliminar(reserva: ReservaItem): Promise<void> {
    if (
      !confirm(
        `Eliminar por completo la reserva #${reserva.id} de ${reserva.cliente_nombre}? Esto no se puede deshacer.`,
      )
    ) {
      return;
    }
    this.procesando.set(reserva.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.delete(`${environment.apiUrl}/reservas/${reserva.id}`));
      await this.load();
    } catch {
      this.error.set('No se pudo eliminar la reserva.');
    } finally {
      this.procesando.set(null);
    }
  }

  // ---------- Editar (sucursal, talla, color, cantidad, horario) ----------
  // Se edita solo el primer item de la reserva -- en la practica el
  // cliente siempre reserva una sola combinacion por reserva, el modelo de
  // datos soporta varias pero la pantalla de creacion nunca arma mas de
  // una.

  protected abrirEditar(reserva: ReservaItem): void {
    const item = reserva.detalles[0];
    this.editando.set(reserva);
    this.editSucursalId.set(reserva.sucursal_id);
    this.editProductoId.set(item?.producto_id ?? null);
    this.editCantidad.set(item?.cantidad ?? 1);
    this.editHorario.set(reserva.horario_atencion.slice(0, 16));
    this.editError.set('');

    const tallaOpcion = this.tallas().find((t) => t.nombre === item?.talla_codigo);
    const colorOpcion = this.colores().find((c) => c.nombre === item?.color_nombre);
    this.editTallaId.set(tallaOpcion?.id ?? null);
    this.editColorId.set(colorOpcion?.id ?? null);
  }

  protected cerrarEditar(): void {
    this.editando.set(null);
  }

  protected async guardarEdicion(): Promise<void> {
    const reserva = this.editando();
    const sucursalId = this.editSucursalId();
    const tallaId = this.editTallaId();
    const colorId = this.editColorId();
    const productoId = this.editProductoId();
    if (!reserva || !sucursalId || !tallaId || !colorId || !productoId || !this.editHorario()) return;

    this.editGuardando.set(true);
    this.editError.set('');
    try {
      await firstValueFrom(
        this.http.put(`${environment.apiUrl}/reservas/${reserva.id}`, {
          sucursal_id: sucursalId,
          horario_atencion: new Date(this.editHorario()).toISOString(),
          items: [{ producto_id: productoId, talla_id: tallaId, color_id: colorId, cantidad: this.editCantidad() }],
        }),
      );
      this.editando.set(null);
      await this.load();
    } catch (err) {
      this.editError.set(this.extraerError(err));
    } finally {
      this.editGuardando.set(false);
    }
  }

  private extraerError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
    }
    return 'No se pudo guardar los cambios.';
  }
}
