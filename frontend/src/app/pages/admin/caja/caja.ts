import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import { mensajeError } from '../../../services/plataforma';

interface ResumenCaja {
  ventas: number;
  total_ventas: string;
  efectivo: string;
  qr: string;
  paypal: string;
  otros: string;
  ingresos: string;
  retiros: string;
  devoluciones_efectivo: string;
  efectivo_esperado: string | null;
}

export interface Caja {
  id: number;
  tipo: 'fisica' | 'online';
  estado: 'abierta' | 'cerrada';
  sucursal_id: number | null;
  sucursal_nombre: string | null;
  fecha: string;
  abierta_en: string;
  abierta_por_nombre: string | null;
  abierta_por_rol: string | null;
  cerrada_en: string | null;
  cerrada_por_nombre: string | null;
  monto_inicial: string;
  efectivo_esperado: string | null;
  efectivo_contado: string | null;
  diferencia: string | null;
  observacion: string | null;
  resumen: ResumenCaja;
}

interface MovimientoCaja {
  id: number;
  tipo: 'ingreso' | 'retiro';
  monto: string;
  motivo: string;
  usuario_nombre: string | null;
  fecha: string;
}

interface VentaCaja {
  id: number;
  fecha: string;
  tipo: string;
  origen: string;
  estado: string;
  cliente: string;
  metodo_pago: string | null;
  estado_pago: string | null;
  atendido_por: string | null;
  total: string;
  fuera_de_arqueo: boolean;
}

interface CajaDetalle extends Caja {
  movimientos: MovimientoCaja[];
  ventas_detalle: VentaCaja[];
}

interface SucursalCaja {
  id: number;
  nombre: string;
  horario_atencion: string | null;
  caja: Caja | null;
}

interface PanelCaja {
  sucursales: SucursalCaja[];
  online: Caja | null;
  puede_operar: boolean;
}

type Accion =
  | { tipo: 'abrir'; sucursal: SucursalCaja }
  | { tipo: 'movimiento'; caja: Caja }
  | { tipo: 'cerrar'; caja: Caja };

export const ROL_LABEL: Record<string, string> = {
  administrador: 'Administrador',
  encargado_sucursal: 'Encargado de sucursal',
  cajero: 'Cajero',
};

const METODO_LABEL: Record<string, string> = {
  efectivo: 'Efectivo',
  qr: 'QR',
  paypal: 'PayPal',
  transferencia: 'Transferencia',
  otro: 'Otro',
};

// CU16 Arqueo y cierre de caja. La caja física la abre el personal de la
// sucursal con su fondo inicial y la cierra contando el efectivo; la caja
// online (una por día) se abre y se cierra sola con las ventas en línea.
// Abajo, el historial de cajas con todas sus ventas. El SuperAdministrador
// elige la tienda y solo mira.
@Component({
  selector: 'app-admin-caja',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './caja.html',
  styleUrls: ['../ventas/ventas.scss', './caja.scss'],
})
export class AdminCaja implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly api = `${environment.apiUrl}/cajas`;

  protected readonly rolLabel = ROL_LABEL;
  protected readonly metodoLabel = METODO_LABEL;
  protected readonly esPlataforma = this.auth.currentUser()?.tipo === 'superadministrador';
  // Encargado y Cajero ven solo su sucursal (el backend ya lo limita).
  protected readonly esAdmin = this.auth.isAdmin();

  protected readonly panel = signal<PanelCaja | null>(null);
  protected readonly historial = signal<Caja[]>([]);
  protected readonly cargando = signal(true);
  protected readonly cargandoHistorial = signal(true);
  protected readonly error = signal('');

  protected readonly filtroSucursal = signal('');
  protected readonly filtroTipo = signal('');

  protected readonly detalle = signal<CajaDetalle | null>(null);
  protected readonly cargandoDetalle = signal<number | null>(null);

  protected readonly accion = signal<Accion | null>(null);
  protected readonly monto = signal('');
  protected readonly tipoMovimiento = signal<'retiro' | 'ingreso'>('retiro');
  protected readonly texto = signal('');
  protected readonly errorAccion = signal('');
  protected readonly procesando = signal(false);

  protected readonly puedeOperar = computed(() => this.panel()?.puede_operar ?? false);

  // Al cerrar: lo contado contra lo esperado, mientras el cajero escribe.
  protected readonly diferenciaCierre = computed(() => {
    const a = this.accion();
    if (a?.tipo !== 'cerrar' || this.monto().trim() === '') return null;
    const contado = Number(this.monto());
    if (Number.isNaN(contado)) return null;
    return contado - Number(a.caja.resumen.efectivo_esperado ?? 0);
  });

  ngOnInit(): void {
    void this.cargarTodo();
  }

  protected async cargarTodo(): Promise<void> {
    await Promise.all([this.cargarPanel(), this.cargarHistorial()]);
  }

  private async cargarPanel(): Promise<void> {
    this.cargando.set(true);
    this.error.set('');
    try {
      this.panel.set(await firstValueFrom(this.http.get<PanelCaja>(`${this.api}/panel`)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar el estado de las cajas.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected async cargarHistorial(): Promise<void> {
    this.cargandoHistorial.set(true);
    try {
      const params: Record<string, string> = {};
      if (this.filtroSucursal()) params['sucursal_id'] = this.filtroSucursal();
      if (this.filtroTipo()) params['tipo'] = this.filtroTipo();
      this.historial.set(await firstValueFrom(this.http.get<Caja[]>(this.api, { params })));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar el historial de cajas.'));
    } finally {
      this.cargandoHistorial.set(false);
    }
  }

  protected numero(valor: string | null): number {
    return Number(valor ?? 0);
  }

  // Las fechas llegan en UTC sin zona; se muestran en hora de Bolivia.
  protected utc(fecha: string): string {
    return fecha.endsWith('Z') ? fecha : `${fecha}Z`;
  }

  protected async verDetalle(caja: Caja): Promise<void> {
    this.cargandoDetalle.set(caja.id);
    this.error.set('');
    try {
      this.detalle.set(await firstValueFrom(this.http.get<CajaDetalle>(`${this.api}/${caja.id}`)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos abrir el detalle de la caja.'));
    } finally {
      this.cargandoDetalle.set(null);
    }
  }

  protected cerrarDetalle(): void {
    this.detalle.set(null);
  }

  protected imprimir(): void {
    window.print();
  }

  protected abrirAccion(accion: Accion): void {
    this.accion.set(accion);
    this.monto.set('');
    this.texto.set('');
    this.tipoMovimiento.set('retiro');
    this.errorAccion.set('');
  }

  protected cerrarAccion(): void {
    if (!this.procesando()) this.accion.set(null);
  }

  protected async confirmar(): Promise<void> {
    const a = this.accion();
    if (!a) return;
    const monto = Number(this.monto());
    if (this.monto().trim() === '' || Number.isNaN(monto) || monto < 0) {
      this.errorAccion.set('Escribe un monto válido (0 o más).');
      return;
    }
    let url: string;
    let cuerpo: object;
    if (a.tipo === 'abrir') {
      url = `${this.api}/abrir`;
      cuerpo = { sucursal_id: a.sucursal.id, monto_inicial: monto };
    } else if (a.tipo === 'movimiento') {
      if (monto <= 0) {
        this.errorAccion.set('El monto debe ser mayor a 0.');
        return;
      }
      if (this.texto().trim().length < 3) {
        this.errorAccion.set('Escribe el motivo del movimiento.');
        return;
      }
      url = `${this.api}/${a.caja.id}/movimientos`;
      cuerpo = { tipo: this.tipoMovimiento(), monto, motivo: this.texto().trim() };
    } else {
      const dif = this.diferenciaCierre() ?? 0;
      if (Math.abs(dif) >= 0.01 && this.texto().trim().length < 3) {
        this.errorAccion.set('Hay diferencia entre lo contado y lo esperado: explica el motivo en la observación.');
        return;
      }
      url = `${this.api}/${a.caja.id}/cerrar`;
      cuerpo = { efectivo_contado: monto, observacion: this.texto().trim() || null };
    }
    this.procesando.set(true);
    this.errorAccion.set('');
    try {
      const res = await firstValueFrom(this.http.post<Caja | CajaDetalle>(url, cuerpo));
      this.accion.set(null);
      await this.cargarTodo();
      // Al cerrar, queda a la vista el arqueo con sus ventas.
      if (a.tipo === 'cerrar') this.detalle.set(res as CajaDetalle);
    } catch (err) {
      this.errorAccion.set(mensajeError(err, 'No se pudo completar la acción.'));
    } finally {
      this.procesando.set(false);
    }
  }
}
