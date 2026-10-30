import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Auth } from '../auth';
import { EstadoOperacion, NoPagado, OfflineDb, OperacionLocal, RegistroSync } from './offline-db';

interface ResultadoServidor {
  uuid: string;
  estado: EstadoOperacion;
  mensaje: string | null;
  venta_id: number | null;
  reserva_id: number | null;
  no_pagados?: NoPagado[] | null;
  total_cobrado?: string | null;
}

// Cobro con el PayPal guardado ya resuelto (se avisa una vez).
export const COBRO_TERMINADO: EstadoOperacion[] = ['pagada', 'pago_parcial', 'no_pagada'];

// Estados que todavía hay que mandar al servidor.
const POR_ENVIAR: EstadoOperacion[] = ['pendiente', 'enviando', 'error'];
// Estados que el servidor todavía puede cambiar (el encargado resuelve el conflicto).
// (el encargado resuelve el conflicto; la compra se paga o se queda sin stock).
// (o la compra con PayPal guardado quedó por cobrar: se cobra al consultar).
const POR_CONSULTAR: EstadoOperacion[] = ['conflicto', 'por_pagar', 'sin_stock', 'por_cobrar'];
const LOTE = 50;
// Lo pendiente tiene prioridad: se envía apenas vuelve la conexión y, si el
// servidor no responde (p. ej. estaba dormido), se reintenta a los 3, 6, 12 y
// 24 s y después cada 15 s mientras quede algo por enviar. (La descarga del
// catálogo, en cambio, es cada 3 minutos: ver descarga-automatica.ts.)
const REINTENTO_MS = 15_000;
const REINTENTOS_RAPIDOS_MS = [3_000, 6_000, 12_000, 24_000];
// Etiqueta del Background Sync que atiende public/sw-arlani.js.
const ETIQUETA_SYNC = 'arlani-sync';
// Un mismo error se anota en el historial como mucho cada 10 minutos.
const REPETIR_ERROR_MS = 10 * 60_000;
// "Sincronizando…" solo si el envío tarda de verdad (sin parpadeos).
const MOSTRAR_OCUPADO_MS = 600;

// CU12 Sincronizar operaciones pendientes. Guarda cada operación hecha sin
// conexión en IndexedDB con su uuid y la manda al volver la conexión (sola,
// cada minuto mientras queden pendientes, o con "Sincronizar ahora"). Una
// operación nunca se borra por haber intentado enviarla: solo cambia de
// estado con la respuesta del servidor; si falla la red vuelve a pendiente.
// Con la app cerrada, el service worker (Background Sync) las envía apenas
// vuelve la conexión.
@Injectable({ providedIn: 'root' })
export class Sincronizacion {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly db = inject(OfflineDb);
  private readonly api = `${environment.apiUrl}/offline`;

  readonly enLinea = signal(navigator.onLine);
  readonly operaciones = signal<OperacionLocal[]>([]);
  readonly registro = signal<RegistroSync[]>([]);
  readonly sincronizando = signal(false);
  // Para la vista: se enciende solo si la sincronización tarda.
  readonly ocupado = signal(false);
  // Sube cada vez que termina una sincronización (p. ej. para revisar si
  // quedaron compras por pagar).
  readonly sincronizaciones = signal(0);
  readonly ultimoError = signal('');

  readonly pendientes = computed(() => this.operaciones().filter((o) => POR_ENVIAR.includes(o.estado)).length);
  readonly conflictos = computed(() => this.operaciones().filter((o) => o.estado === 'conflicto').length);
  // Compras con PayPal guardado ya cobradas (o no) que el cliente no vio.
  readonly cobros = computed(() =>
    this.operaciones().filter((o) => o.forma_pago === 'paypal_guardado' && COBRO_TERMINADO.includes(o.estado) && !o.cobro_visto),
  );

  private usuarioId: number | null = null;
  private ultimoErrorAnotado = { detalle: '', en: 0 };
  private reintento: ReturnType<typeof setTimeout> | null = null;
  private reintentosHechos = 0;

  constructor() {
    window.addEventListener('online', () => {
      this.enLinea.set(true);
      this.reintentosHechos = 0;
      void this.sincronizar();
    });
    window.addEventListener('offline', () => this.enLinea.set(false));
    // Al volver a la pestaña o a la app instalada.
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') void this.sincronizar();
    });
    setInterval(() => {
      if (this.enLinea() && this.pendientes() > 0) void this.sincronizar();
    }, REINTENTO_MS);
    // El service worker avisa cuando sincronizó con la app cerrada o en segundo plano.
    navigator.serviceWorker?.addEventListener('message', (e: MessageEvent) => {
      if ((e.data as { tipo?: string } | null)?.tipo === 'arlani-sincronizado') void this.cargar();
    });
    // Las operaciones son de cada usuario: se cargan al iniciar sesión.
    effect(() => {
      const id = this.auth.currentUser()?.id ?? null;
      if (id === this.usuarioId) return;
      this.usuarioId = id;
      this.operaciones.set([]);
      this.registro.set([]);
      if (id !== null) untracked(() => void this.cargar().then(() => this.sincronizar()));
    });
    // El service worker necesita el token para sincronizar sin la app abierta.
    effect(() => {
      const id = this.auth.currentUser()?.id ?? null;
      const token = this.auth.token();
      if (id !== null && token) void this.db.guardarSesion({ usuario_id: id, token, api: this.api });
      else void this.db.borrarSesiones();
    });
  }

  async cargar(): Promise<void> {
    if (this.usuarioId === null) return;
    this.operaciones.set(await this.db.operaciones(this.usuarioId));
    this.registro.set(await this.db.registro(this.usuarioId));
  }

  // Registra una operación en el dispositivo (sin conexión o con ella).
  async registrar(
    op: Omit<OperacionLocal, 'uuid' | 'usuario_id' | 'registrada_en' | 'estado' | 'mensaje' | 'venta_id' | 'reserva_id' | 'intentos' | 'ultimo_intento'>,
  ): Promise<OperacionLocal> {
    if (this.usuarioId === null) throw new Error('Sin sesión');
    const nueva: OperacionLocal = {
      ...op,
      uuid: crypto.randomUUID(),
      usuario_id: this.usuarioId,
      registrada_en: new Date().toISOString(),
      estado: 'pendiente',
      mensaje: null,
      venta_id: null,
      reserva_id: null,
      intentos: 0,
      ultimo_intento: null,
    };
    await this.db.guardarOperacion(nueva);
    await this.cargar();
    if (this.enLinea()) void this.sincronizar();
    else void this.pedirSyncEnFondo();
    return nueva;
  }

  async marcarCobrosVistos(): Promise<void> {
    for (const op of this.cobros()) await this.db.guardarOperacion({ ...op, cobro_visto: true });
    await this.cargar();
  }

  async sincronizar(): Promise<void> {
    if (this.sincronizando() || this.usuarioId === null || !this.auth.token()) return;
    const usuario = this.usuarioId;
    const porEnviar = this.operaciones().filter((o) => POR_ENVIAR.includes(o.estado));
    const porConsultar = this.operaciones().filter((o) => POR_CONSULTAR.includes(o.estado));
    if (!porEnviar.length && !porConsultar.length) return;

    this.sincronizando.set(true);
    const aviso = setTimeout(() => this.ocupado.set(true), MOSTRAR_OCUPADO_MS);
    const cuenta = { enviadas: 0, confirmadas: 0, conflictos: 0, rechazadas: 0, errores: 0 };
    try {
      for (let i = 0; i < porEnviar.length; i += LOTE) {
        const lote = porEnviar.slice(i, i + LOTE);
        const ahora = new Date().toISOString();
        for (const op of lote) await this.db.guardarOperacion({ ...op, estado: 'enviando', ultimo_intento: ahora, intentos: op.intentos + 1 });
        let resultados: ResultadoServidor[];
        try {
          resultados = await firstValueFrom(
            this.http.post<ResultadoServidor[]>(`${this.api}/sincronizar`, { operaciones: lote.map((o) => this.contrato(o)) }),
          );
        } catch (err) {
          // Sin respuesta del servidor: quedan pendientes, se reintentan.
          for (const op of lote) await this.db.guardarOperacion({ ...op, estado: 'pendiente', ultimo_intento: ahora, intentos: op.intentos + 1 });
          this.ultimoError.set(this.motivo(err));
          cuenta.errores += lote.length;
          this.programarReintento();
          void this.pedirSyncEnFondo();
          break;
        }
        cuenta.enviadas += lote.length;
        this.reintentosHechos = 0;
        this.ultimoError.set('');
        for (const op of lote) {
          const r = resultados.find((x) => x.uuid === op.uuid);
          if (!r) continue;
          await this.aplicar({ ...op, intentos: op.intentos + 1, ultimo_intento: ahora }, r);
          if (r.estado === 'confirmada') cuenta.confirmadas++;
          else if (r.estado === 'conflicto') cuenta.conflictos++;
          else if (r.estado === 'rechazada') cuenta.rechazadas++;
          else if (r.estado === 'error') cuenta.errores++;
        }
      }
      if (porConsultar.length) {
        try {
          const estados = await firstValueFrom(
            this.http.post<ResultadoServidor[]>(`${this.api}/estado`, { uuids: porConsultar.map((o) => o.uuid) }),
          );
          for (const r of estados) {
            const op = porConsultar.find((o) => o.uuid === r.uuid);
            if (op && r.estado !== op.estado) await this.aplicar(op, r);
          }
        } catch {
          // Se vuelve a consultar en el próximo intento.
        }
      }
    } finally {
      // Al historial: lo que llegó al servidor siempre; un mismo error de
      // conexión, no en cada reintento.
      const detalle = this.ultimoError() || 'Sincronización completada.';
      const errorRepetido =
        !cuenta.enviadas &&
        detalle === this.ultimoErrorAnotado.detalle &&
        Date.now() - this.ultimoErrorAnotado.en < REPETIR_ERROR_MS;
      if ((cuenta.enviadas || cuenta.errores) && !errorRepetido) {
        await this.db.registrar({ usuario_id: usuario, fecha: new Date().toISOString(), ...cuenta, detalle });
        if (!cuenta.enviadas) this.ultimoErrorAnotado = { detalle, en: Date.now() };
      }
      clearTimeout(aviso);
      this.ocupado.set(false);
      this.sincronizando.set(false);
      await this.cargar();
      this.sincronizaciones.update((n) => n + 1);
    }
  }

  private programarReintento(): void {
    if (this.reintento || this.reintentosHechos >= REINTENTOS_RAPIDOS_MS.length) return;
    const espera = REINTENTOS_RAPIDOS_MS[this.reintentosHechos++];
    this.reintento = setTimeout(() => {
      this.reintento = null;
      if (this.enLinea()) void this.sincronizar();
    }, espera);
  }

  // Background Sync (Chrome/Edge, también en Android): el navegador despierta
  // al service worker cuando vuelve la conexión, aunque la app esté cerrada.
  private async pedirSyncEnFondo(): Promise<void> {
    try {
      const registro = await navigator.serviceWorker?.getRegistration();
      const sync = (registro as (ServiceWorkerRegistration & { sync?: { register(tag: string): Promise<void> } }) | undefined)
        ?.sync;
      await sync?.register(ETIQUETA_SYNC);
    } catch {
      // Sin soporte: se envía al volver la conexión con la app abierta.
    }
  }

  private async aplicar(op: OperacionLocal, r: ResultadoServidor): Promise<void> {
    await this.db.guardarOperacion({
      ...op,
      // "error": el servidor no la pudo guardar; se reintenta.
      estado: r.estado,
      mensaje: r.mensaje,
      venta_id: r.venta_id ?? op.venta_id,
      reserva_id: r.reserva_id ?? op.reserva_id,
      no_pagados: r.no_pagados ?? null,
      total_cobrado: r.total_cobrado ?? null,
    });
  }

  // Lo que viaja al servidor (el mismo contrato que usa la app Flutter).
  private contrato(o: OperacionLocal): object {
    return {
      uuid: o.uuid,
      tipo: o.tipo,
      sucursal_id: o.sucursal_id,
      registrada_en: o.registrada_en,
      cliente_id: o.cliente_id,
      factura_nombre: o.factura_nombre,
      factura_nit: o.factura_nit,
      horario_atencion: o.horario_atencion,
      entrega: o.entrega ?? 'retiro',
      direccion_id: o.direccion_id ?? null,
      forma_pago: o.forma_pago ?? null,
      items: o.items.map((i) => ({
        producto_id: i.producto_id,
        talla_id: i.talla_id,
        color_id: i.color_id,
        cantidad: i.cantidad,
        precio: i.precio,
      })),
    };
  }

  private motivo(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 0 || err.status === 504) return 'Sin conexión con el servidor: se reintentará.';
      if (err.status === 401) return 'Tu sesión venció: inicia sesión para terminar de sincronizar (tus operaciones siguen guardadas).';
      const detalle = (err.error as { detail?: unknown } | null)?.detail;
      if (typeof detalle === 'string') return detalle;
    }
    return 'No se pudo sincronizar: se reintentará.';
  }
}
