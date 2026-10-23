import { DatePipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Auth } from '../../services/auth';
import { Notificaciones } from '../../services/notificaciones';
import { checkPassword, isPasswordValid } from '../../utils/password';
import { MisCambios } from './mis-cambios/mis-cambios';
import { MisDirecciones } from './mis-direcciones/mis-direcciones';

interface DetalleReservaItem {
  id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad: number;
}

interface ReservaItem {
  id: number;
  sucursal_nombre: string;
  horario_atencion: string;
  estado: string;
  detalles: DetalleReservaItem[];
}

interface DetalleVentaItem {
  id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad: number;
  precio_unitario: string;
  ya_solicitada: boolean;
}

interface VentaItem {
  id: number;
  tipo: string;
  sucursal_nombre: string;
  fecha: string;
  total: string;
  estado: string;
  metodo_pago: string;
  metodo_pago_nombre: string | null;
  motivo_rechazo: string | null;
  tienda: { nombre: string } | null;
  envio: { direccion: string; ciudad: string | null; estado: string } | null;
  estado_pago: string;
  calificacion_estrellas: number | null;
  calificacion_comentario: string | null;
  detalles: DetalleVentaItem[];
  tiene_devolucion?: boolean;
  estado_devolucion?: string | null;
  monto_devolucion?: string | null;
  puede_devolver?: boolean;
  puede_cambiar?: boolean;
  horas_restantes_devolucion?: number | null;
}

interface ItemDevolucionSeleccion {
  item_linea_id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad_comprada: number;
  cantidad_devuelta: number;
  precio_unitario: number;
  seleccionado: boolean;
}

type Tab =
  | 'resumen'
  | 'reservas'
  | 'compras'
  | 'cambios'
  | 'devoluciones'
  | 'direcciones'
  | 'pagos'
  | 'notificaciones'
  | 'datos'
  | 'seguridad';

// Cambio de una prenda comprada (para tacharla en Mis Compras).
interface CambioDeLinea {
  id: number;
  item_linea_id: number;
  estado: string;
  cantidad: number;
  producto_nuevo: string;
  talla_nueva: string;
  color_nuevo: string;
}

interface DevolucionCliente {
  id: number;
  venta_id: number;
  tienda_nombre: string;
  sucursal_nombre: string;
  venta_fecha: string;
  motivo: string;
  tipo: string;
  monto_reembolso: string;
  metodo_reembolso: string;
  estado: string;
  fecha_solicitud: string;
  fecha_resolucion: string | null;
  observaciones: string | null;
  detalles: { id: number; producto_nombre: string; talla_codigo: string; color_nombre: string; cantidad_devuelta: number }[];
}

const METODO_LABEL: Record<string, string> = {
  paypal: 'PayPal / Tarjeta',
  qr: 'QR',
  transferencia: 'Transferencia',
  otro: 'Otro',
  efectivo: 'Efectivo en sucursal',
};

const ESTADO_PAGO_LABEL: Record<string, string> = {
  completado: 'pagado',
  verificando: 'en revisión',
  rechazado: 'rechazado',
  pendiente: 'pendiente',
};

@Component({
  selector: 'app-perfil',
  imports: [RouterLink, DatePipe, MisCambios, MisDirecciones],
  templateUrl: './perfil.html',
  styleUrl: './perfil.scss',
})
export class Perfil implements OnInit {
  protected readonly auth = inject(Auth);
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  protected readonly notificaciones = inject(Notificaciones);

  protected readonly isCliente = computed(() => this.auth.currentUser()?.tipo === 'cliente');
  protected readonly metodoLabel = METODO_LABEL;
  protected readonly estadoPagoLabel = ESTADO_PAGO_LABEL;

  protected readonly tab = signal<Tab>('resumen');

  // ---------- Reservas y compras (solo clientes) ----------
  protected readonly reservas = signal<ReservaItem[]>([]);
  protected readonly compras = signal<VentaItem[]>([]);
  protected readonly cargandoReservas = signal(false);
  protected readonly cargandoCompras = signal(false);
  protected readonly procesandoReserva = signal<number | null>(null);

  protected readonly reservasActivas = computed(
    () => this.reservas().filter((r) => r.estado === 'pendiente' || r.estado === 'confirmada').length,
  );
  protected readonly totalGastado = computed(() =>
    this.compras()
      .filter((v) => v.estado_pago === 'completado')
      .reduce((sum, v) => sum + Number(v.total), 0)
      .toFixed(2),
  );
  protected readonly metodosUsados = computed(() => {
    const conteo = new Map<string, number>();
    for (const v of this.compras()) {
      if (v.estado_pago !== 'completado') continue;
      conteo.set(v.metodo_pago, (conteo.get(v.metodo_pago) ?? 0) + 1);
    }
    return Array.from(conteo.entries()).map(([metodo, veces]) => ({ metodo, veces }));
  });

  // ---------- Datos personales ----------
  protected readonly nombre = signal(this.auth.currentUser()?.nombre ?? '');
  protected readonly telefono = signal(this.auth.currentUser()?.telefono ?? '');
  protected readonly direccion = signal(this.auth.currentUser()?.direccion ?? '');
  protected readonly profileError = signal('');
  protected readonly profileSuccess = signal('');
  protected readonly profileSaving = signal(false);

  // ---------- Contrasena ----------
  protected readonly passwordActual = signal('');
  protected readonly passwordNueva = signal('');
  protected readonly passwordConfirmar = signal('');
  protected readonly showActual = signal(false);
  protected readonly showNueva = signal(false);
  protected readonly showConfirmar = signal(false);
  protected readonly passwordTouched = signal(false);
  protected readonly passwordChecks = computed(() => checkPassword(this.passwordNueva()));
  protected readonly passwordError = signal('');
  protected readonly passwordSuccess = signal('');
  protected readonly passwordSaving = signal(false);

  ngOnInit(): void {
    if (this.isCliente()) {
      void this.cargarReservas();
      void this.cargarCompras();
      void this.cargarCambios();
      void this.notificaciones.cargar();
    }

    const tabParam = this.route.snapshot.queryParamMap.get('tab') as Tab | null;
    if (tabParam) this.setTab(tabParam);
  }

  protected setTab(t: Tab): void {
    this.tab.set(t);
    if (t === 'devoluciones') void this.cargarDevoluciones();
    if (t === 'compras') void this.cargarCambios();
  }

  private async cargarReservas(): Promise<void> {
    this.cargandoReservas.set(true);
    try {
      const res = await firstValueFrom(this.http.get<ReservaItem[]>(`${environment.apiUrl}/reservas/mias`));
      this.reservas.set(res);
    } catch {
      this.reservas.set([]);
    } finally {
      this.cargandoReservas.set(false);
    }
  }

  private async cargarCompras(): Promise<void> {
    this.cargandoCompras.set(true);
    try {
      const res = await firstValueFrom(this.http.get<VentaItem[]>(`${environment.apiUrl}/ventas/mias`));
      this.compras.set(res);
    } catch {
      this.compras.set([]);
    } finally {
      this.cargandoCompras.set(false);
    }
  }

  // ---------- Cambio de prendas (24 horas desde la compra) ----------
  private readonly misCambios = viewChild(MisCambios);

  // Pasaron las 24 h desde la compra (para el aviso de plazo vencido).
  protected vencioPlazo(v: VentaItem): boolean {
    const fecha = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(v.fecha) ? v.fecha : v.fecha + 'Z');
    return Date.now() - fecha > 24 * 3600 * 1000;
  }

  // Alguna prenda ya tuvo su unica solicitud de cambio o devolucion.
  protected algunaSolicitada(v: VentaItem): boolean {
    return v.detalles.some((d) => d.ya_solicitada);
  }

  protected abrirCambio(v: VentaItem): void {
    void this.misCambios()?.abrir(v.id);
  }

  // Tras pedir un cambio: la prenda se tacha y la compra ya no ofrece otro.
  protected alPedirCambio(): void {
    void this.cargarCambios();
    void this.cargarCompras();
  }

  // Cambios pedidos por linea de compra: en Mis Compras la prenda que se
  // cambia sale tachada, con la nueva al lado (rechazados y cancelados no).
  private readonly cambiosDeLineas = signal<CambioDeLinea[]>([]);
  protected readonly cambioPorLinea = computed(() => {
    const m = new Map<number, CambioDeLinea>();
    for (const c of this.cambiosDeLineas()) {
      if (c.estado !== 'rechazado' && c.estado !== 'cancelado' && !m.has(c.item_linea_id)) m.set(c.item_linea_id, c);
    }
    return m;
  });
  protected readonly estadoCambioLabel: Record<string, string> = {
    solicitado: 'cambio por revisar',
    por_pagar: 'cambio: falta pagar la diferencia',
    verificando: 'cambio: comprobante en revisión',
    completado: 'cambiada',
  };

  protected async cargarCambios(): Promise<void> {
    try {
      this.cambiosDeLineas.set(await firstValueFrom(this.http.get<CambioDeLinea[]>(`${environment.apiUrl}/cambios/mios`)));
    } catch {
      this.cambiosDeLineas.set([]);
    }
  }

  // ---------- Mis devoluciones ----------
  protected readonly devoluciones = signal<DevolucionCliente[]>([]);
  protected readonly cargandoDevoluciones = signal(false);
  protected readonly estadoDevolucionLabel: Record<string, string> = {
    solicitada: 'En revisión',
    aprobada: 'Aprobada',
    completada: 'Aprobada y reembolsada',
    rechazada: 'Rechazada',
  };
  protected readonly metodoReembolsoLabel: Record<string, string> = {
    mismo_medio: 'al mismo medio de pago',
    credito_tienda: 'como crédito en la tienda',
    efectivo: 'en efectivo en la sucursal',
  };
  protected readonly motivoDevolucionLabel: Record<string, string> = {
    defecto: 'Defecto de fábrica',
    talla_incorrecta: 'Talla incorrecta',
    insatisfaccion: 'No cumplió expectativas',
    otro: 'Otro motivo',
  };

  private async cargarDevoluciones(): Promise<void> {
    this.cargandoDevoluciones.set(true);
    try {
      this.devoluciones.set(
        await firstValueFrom(this.http.get<DevolucionCliente[]>(`${environment.apiUrl}/devoluciones/mias`)),
      );
    } catch {
      this.devoluciones.set([]);
    } finally {
      this.cargandoDevoluciones.set(false);
    }
  }

  // ---------- Calificar una compra (CU20) ----------
  protected readonly calificandoVentaId = signal<number | null>(null);
  protected readonly estrellasSeleccionadas = signal(0);
  protected readonly comentarioCalificacion = signal('');
  protected readonly guardandoCalificacion = signal(false);
  protected readonly errorCalificacion = signal('');

  protected abrirCalificar(venta: VentaItem): void {
    this.calificandoVentaId.set(venta.id);
    this.estrellasSeleccionadas.set(0);
    this.comentarioCalificacion.set('');
    this.errorCalificacion.set('');
  }

  protected cerrarCalificar(): void {
    this.calificandoVentaId.set(null);
  }

  protected async enviarCalificacion(venta: VentaItem): Promise<void> {
    const estrellas = this.estrellasSeleccionadas();
    if (estrellas < 1) return;

    this.guardandoCalificacion.set(true);
    this.errorCalificacion.set('');
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/calificaciones/venta/${venta.id}`, {
          estrellas,
          comentario: this.comentarioCalificacion().trim() || null,
        }),
      );
      this.compras.update((items) =>
        items.map((v) =>
          v.id === venta.id
            ? { ...v, calificacion_estrellas: estrellas, calificacion_comentario: this.comentarioCalificacion().trim() || null }
            : v,
        ),
      );
      this.calificandoVentaId.set(null);
    } catch (err) {
      this.errorCalificacion.set(this.extractError(err));
    } finally {
      this.guardandoCalificacion.set(false);
    }
  }

  // ---------- Solicitar Devolucion (CU11 - Cliente, 24 horas) ----------
  protected readonly devolviendoVenta = signal<VentaItem | null>(null);
  protected readonly itemsDevolucion = signal<ItemDevolucionSeleccion[]>([]);
  protected readonly motivoDevolucion = signal<'defecto' | 'talla_incorrecta' | 'insatisfaccion' | 'otro'>('defecto');
  protected readonly metodoReembolso = signal<'mismo_medio' | 'credito_tienda' | 'efectivo'>('mismo_medio');
  protected readonly observacionesDevolucion = signal('');
  protected readonly guardandoDevolucion = signal(false);
  protected readonly errorDevolucion = signal('');
  protected readonly exitoDevolucion = signal('');

  protected readonly montoReembolsoTotal = computed(() => {
    return this.itemsDevolucion()
      .filter((i) => i.seleccionado)
      .reduce((sum, i) => sum + i.precio_unitario * i.cantidad_devuelta, 0)
      .toFixed(2);
  });

  protected readonly tieneItemsSeleccionados = computed(() => {
    return this.itemsDevolucion().some((i) => i.seleccionado && i.cantidad_devuelta > 0);
  });

  protected estaEnPlazo24h(v: VentaItem): boolean {
    if (v.puede_devolver !== undefined) {
      return v.puede_devolver;
    }
    const fecha = new Date(v.fecha).getTime();
    const diffHoras = (Date.now() - fecha) / (1000 * 60 * 60);
    return diffHoras <= 24 && v.estado_pago === 'completado' && !v.tiene_devolucion;
  }

  protected horasRestantes(v: VentaItem): string {
    if (v.horas_restantes_devolucion !== null && v.horas_restantes_devolucion !== undefined) {
      const horas = Math.floor(v.horas_restantes_devolucion);
      const minutos = Math.round((v.horas_restantes_devolucion - horas) * 60);
      return `${horas}h ${minutos}m`;
    }
    const fecha = new Date(v.fecha).getTime();
    const diffMs = fecha + 24 * 60 * 60 * 1000 - Date.now();
    if (diffMs <= 0) return '0h';
    const horas = Math.floor(diffMs / (1000 * 60 * 60));
    const minutos = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    return `${horas}h ${minutos}m`;
  }

  protected abrirModalDevolucion(v: VentaItem): void {
    this.devolviendoVenta.set(v);
    this.errorDevolucion.set('');
    this.exitoDevolucion.set('');
    this.observacionesDevolucion.set('');
    this.motivoDevolucion.set('defecto');
    this.metodoReembolso.set('mismo_medio');
    // Solo las prendas que no tuvieron ya su unica solicitud.
    this.itemsDevolucion.set(
      (v.detalles || []).filter((d) => !d.ya_solicitada).map((d) => ({
        item_linea_id: d.id,
        producto_nombre: d.producto_nombre,
        talla_codigo: d.talla_codigo,
        color_nombre: d.color_nombre,
        cantidad_comprada: d.cantidad,
        cantidad_devuelta: d.cantidad,
        precio_unitario: Number(d.precio_unitario) || 0,
        seleccionado: true,
      })),
    );
  }

  protected cerrarModalDevolucion(): void {
    this.devolviendoVenta.set(null);
  }

  protected toggleItemDevolucion(index: number): void {
    this.itemsDevolucion.update((items) =>
      items.map((item, idx) => (idx === index ? { ...item, seleccionado: !item.seleccionado } : item)),
    );
  }

  protected setCantidadDevolucion(index: number, cantidad: number): void {
    this.itemsDevolucion.update((items) =>
      items.map((item, idx) => {
        if (idx !== index) return item;
        const cant = Math.max(1, Math.min(item.cantidad_comprada, cantidad));
        return { ...item, cantidad_devuelta: cant };
      }),
    );
  }

  protected async enviarSolicitudDevolucion(): Promise<void> {
    const venta = this.devolviendoVenta();
    if (!venta) return;

    const itemsAEnviar = this.itemsDevolucion()
      .filter((i) => i.seleccionado && i.cantidad_devuelta > 0)
      .map((i) => ({
        item_linea_id: i.item_linea_id,
        cantidad_devuelta: i.cantidad_devuelta,
      }));

    if (itemsAEnviar.length === 0) {
      this.errorDevolucion.set('Debes seleccionar al menos un producto a devolver.');
      return;
    }

    // Total solo si se devuelve TODA la compra (si alguna prenda quedo fuera
    // por ya tener su solicitud, es parcial).
    const todosCompletos =
      this.itemsDevolucion().length === venta.detalles.length &&
      this.itemsDevolucion().every((i) => i.seleccionado && i.cantidad_devuelta === i.cantidad_comprada);
    const tipo = todosCompletos ? 'total' : 'parcial';

    this.guardandoDevolucion.set(true);
    this.errorDevolucion.set('');

    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/devoluciones/solicitar/${venta.id}`, {
          motivo: this.motivoDevolucion(),
          tipo,
          metodo_reembolso: this.metodoReembolso(),
          observaciones: this.observacionesDevolucion() || null,
          items: itemsAEnviar,
        }),
      );

      this.exitoDevolucion.set('Tu solicitud de devolución fue enviada con éxito. Nuestro personal la revisará.');
      void this.cargarCompras();

      // Actualizar estado reactivamente en compras()
      this.compras.update((items) =>
        items.map((it) =>
          it.id === venta.id
            ? {
                ...it,
                tiene_devolucion: true,
                estado_devolucion: 'solicitada',
                puede_devolver: false,
              }
            : it,
        ),
      );

      setTimeout(() => {
        this.cerrarModalDevolucion();
      }, 1800);
    } catch (err) {
      this.errorDevolucion.set(this.extractError(err));
    } finally {
      this.guardandoDevolucion.set(false);
    }
  }

  protected async cancelarReserva(r: ReservaItem): Promise<void> {
    if (!confirm(`Cancelar tu reserva #${r.id}?`)) return;
    this.procesandoReserva.set(r.id);
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/reservas/${r.id}/cancelar`, {}));
      await this.cargarReservas();
    } catch {
      // el error se ve reflejado simplemente en que la reserva no cambia de estado
    } finally {
      this.procesandoReserva.set(null);
    }
  }

  protected async submitProfile(): Promise<void> {
    if (!this.nombre()) {
      this.profileError.set('El nombre no puede estar vacio.');
      return;
    }

    this.profileError.set('');
    this.profileSuccess.set('');
    this.profileSaving.set(true);
    try {
      await this.auth.updateProfile({
        nombre: this.nombre(),
        telefono: this.telefono() || null,
        direccion: this.direccion() || null,
      });
      this.profileSuccess.set('Tus datos se actualizaron correctamente.');
    } catch (err) {
      this.profileError.set(this.extractError(err));
    } finally {
      this.profileSaving.set(false);
    }
  }

  protected async submitPassword(): Promise<void> {
    this.passwordTouched.set(true);
    this.passwordSuccess.set('');

    if (!this.passwordActual()) {
      this.passwordError.set('Ingresa tu contrasena actual.');
      return;
    }
    if (!isPasswordValid(this.passwordNueva())) {
      this.passwordError.set('La nueva contrasena no cumple los requisitos minimos.');
      return;
    }
    if (this.passwordNueva() !== this.passwordConfirmar()) {
      this.passwordError.set('Las contrasenas no coinciden.');
      return;
    }

    this.passwordError.set('');
    this.passwordSaving.set(true);
    try {
      await this.auth.changePassword(this.passwordActual(), this.passwordNueva());
      this.passwordSuccess.set('Tu contrasena se actualizo. Te avisamos por correo.');
      this.passwordActual.set('');
      this.passwordNueva.set('');
      this.passwordConfirmar.set('');
      this.passwordTouched.set(false);
    } catch (err) {
      this.passwordError.set(this.extractError(err));
    } finally {
      this.passwordSaving.set(false);
    }
  }

  private extractError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'Ocurrio un error inesperado.';
  }
}
