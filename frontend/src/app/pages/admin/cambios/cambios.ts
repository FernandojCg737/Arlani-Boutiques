import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import { mensajeError } from '../../../services/plataforma';

export interface CambioPrenda {
  id: number;
  venta_id: number;
  venta_fecha: string;
  estado: 'solicitado' | 'por_pagar' | 'verificando' | 'completado' | 'rechazado' | 'cancelado';
  motivo: string;
  observaciones: string | null;
  cantidad: number;
  sucursal_nombre: string;
  cliente_nombre: string;
  cliente_email: string;
  producto_original: string;
  talla_original: string;
  color_original: string;
  producto_nuevo: string;
  talla_nueva: string;
  color_nuevo: string;
  precio_pagado: string;
  precio_nuevo: string;
  diferencia: string;
  destino: string | null;
  motivo_rechazo: string | null;
  reembolso_metodo: string | null;
  metodo_pago_nombre: string | null;
  comprobante_url: string | null;
  empleado_nombre: string | null;
  fecha_solicitud: string;
  fecha_completado: string | null;
}

export const ESTADO_CAMBIO: Record<string, string> = {
  solicitado: 'Por revisar',
  por_pagar: 'Espera el pago de la diferencia',
  verificando: 'Comprobante por revisar',
  completado: 'Completado',
  rechazado: 'Rechazado',
  cancelado: 'Cancelado por el cliente',
};

export const MOTIVO_CAMBIO: Record<string, string> = {
  talla: 'Talla',
  color: 'Color',
  modelo: 'Otro modelo',
  defecto: 'Defecto',
  otro: 'Otro',
};

export const DESTINO_PRENDA: Record<string, string> = {
  reingreso: 'Vuelve al stock',
  merma: 'Merma (dañada)',
  proveedor: 'Se devuelve al proveedor',
};

// CU Cambio de prendas (personal): el Administrador, Encargado o Cajero
// revisa los pedidos de cambio, decide qué pasa con la prenda devuelta
// (reingreso, merma o proveedor) y aprueba los pagos de la diferencia.
@Component({
  selector: 'app-admin-cambios',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './cambios.html',
  styleUrls: ['../ventas/ventas.scss', './cambios.scss'],
})
export class AdminCambios implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly api = `${environment.apiUrl}/cambios`;

  protected readonly estadoLabel = ESTADO_CAMBIO;
  protected readonly motivoLabel = MOTIVO_CAMBIO;
  protected readonly destinoLabel = DESTINO_PRENDA;
  // El SuperAdministrador solo mira: no es personal de la tienda.
  protected readonly soloLectura = computed(() => this.auth.currentUser()?.tipo === 'superadministrador');
  // Pantalla propia (CU15 del SuperAdministrador) o pestaña de Gestión de Ventas.
  protected readonly pagina = inject(ActivatedRoute).snapshot.data['pagina'] === true;

  protected readonly cambios = signal<CambioPrenda[]>([]);
  protected readonly filtro = signal('');
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly procesando = signal<number | null>(null);

  // Modal: aprobar (con destino), rechazar o rechazar pago (con motivo).
  protected readonly accion = signal<{ tipo: 'aprobar' | 'rechazar' | 'rechazar-pago'; cambio: CambioPrenda } | null>(null);
  protected readonly destino = signal<'reingreso' | 'merma' | 'proveedor'>('reingreso');
  protected readonly texto = signal('');
  protected readonly errorAccion = signal('');

  protected readonly pendientes = computed(
    () => this.cambios().filter((c) => c.estado === 'solicitado' || c.estado === 'verificando').length,
  );

  ngOnInit(): void {
    void this.cargar();
  }

  protected async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = this.filtro() ? { estado: this.filtro() } : {};
      this.cambios.set(await firstValueFrom(this.http.get<CambioPrenda[]>(this.api, { params })));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar los cambios de prenda.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected filtrar(valor: string): void {
    this.filtro.set(valor);
    void this.cargar();
  }

  protected numero(valor: string): number {
    return Number(valor);
  }

  protected abrir(tipo: 'aprobar' | 'rechazar' | 'rechazar-pago', cambio: CambioPrenda): void {
    this.accion.set({ tipo, cambio });
    this.destino.set(cambio.motivo === 'defecto' ? 'merma' : 'reingreso');
    this.texto.set('');
    this.errorAccion.set('');
  }

  protected cerrar(): void {
    this.accion.set(null);
  }

  protected async confirmar(): Promise<void> {
    const a = this.accion();
    if (!a) return;
    const texto = this.texto().trim();
    if (a.tipo !== 'aprobar' && texto.length < 3) {
      this.errorAccion.set('Escribe el motivo: el cliente lo verá.');
      return;
    }
    const cuerpo =
      a.tipo === 'aprobar' ? { destino: this.destino(), observacion: texto || null } : { motivo: texto };
    await this.ejecutar(a.cambio, a.tipo, cuerpo, true);
  }

  protected async aprobarPago(c: CambioPrenda): Promise<void> {
    if (!confirm(`¿Aprobar el pago de la diferencia del cambio #${c.id}? Se entrega la prenda nueva y se mueve el stock.`)) return;
    await this.ejecutar(c, 'aprobar-pago', {}, false);
  }

  private async ejecutar(c: CambioPrenda, ruta: string, cuerpo: object, enModal: boolean): Promise<void> {
    this.procesando.set(c.id);
    this.errorAccion.set('');
    this.error.set('');
    try {
      const nuevo = await firstValueFrom(this.http.post<CambioPrenda>(`${this.api}/${c.id}/${ruta}`, cuerpo));
      this.cambios.update((cs) => cs.map((x) => (x.id === nuevo.id ? nuevo : x)));
      this.accion.set(null);
    } catch (err) {
      const msg = mensajeError(err, 'No se pudo completar la acción.');
      if (enModal) this.errorAccion.set(msg);
      else this.error.set(msg);
    } finally {
      this.procesando.set(null);
    }
  }
}
