import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Auth } from '../auth';
import { EstadoOperacion, OfflineDb, OperacionLocal, RegistroSync } from './offline-db';

interface ResultadoServidor {
  uuid: string;
  estado: EstadoOperacion;
  mensaje: string | null;
  venta_id: number | null;
  reserva_id: number | null;
}

// Estados que todavía hay que mandar al servidor.
const POR_ENVIAR: EstadoOperacion[] = ['pendiente', 'enviando', 'error'];
// Estados que el servidor todavía puede cambiar (el encargado resuelve el conflicto).
const POR_CONSULTAR: EstadoOperacion[] = ['conflicto'];
const LOTE = 50;
const REINTENTO_MS = 60_000;

// CU12 Sincronizar operaciones pendientes. Guarda cada operación hecha sin
// conexión en IndexedDB con su uuid y la manda al volver la conexión (sola,
// cada minuto mientras queden pendientes, o con "Sincronizar ahora"). Una
// operación nunca se borra por haber intentado enviarla: solo cambia de
// estado con la respuesta del servidor; si falla la red vuelve a pendiente.
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
  readonly ultimoError = signal('');

  readonly pendientes = computed(() => this.operaciones().filter((o) => POR_ENVIAR.includes(o.estado)).length);
  readonly conflictos = computed(() => this.operaciones().filter((o) => o.estado === 'conflicto').length);

  private usuarioId: number | null = null;

  constructor() {
    window.addEventListener('online', () => {
      this.enLinea.set(true);
      void this.sincronizar();
    });
    window.addEventListener('offline', () => this.enLinea.set(false));
    setInterval(() => {
      if (this.enLinea() && this.pendientes() > 0) void this.sincronizar();
    }, REINTENTO_MS);
    // Las operaciones son de cada usuario: se cargan al iniciar sesión.
    effect(() => {
      const id = this.auth.currentUser()?.id ?? null;
      if (id === this.usuarioId) return;
      this.usuarioId = id;
      this.operaciones.set([]);
      this.registro.set([]);
      if (id !== null) void this.cargar().then(() => this.sincronizar());
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
    return nueva;
  }

  async sincronizar(): Promise<void> {
    if (this.sincronizando() || this.usuarioId === null || !this.auth.token()) return;
    const usuario = this.usuarioId;
    const porEnviar = this.operaciones().filter((o) => POR_ENVIAR.includes(o.estado));
    const porConsultar = this.operaciones().filter((o) => POR_CONSULTAR.includes(o.estado));
    if (!porEnviar.length && !porConsultar.length) return;

    this.sincronizando.set(true);
    this.ultimoError.set('');
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
          break;
        }
        cuenta.enviadas += lote.length;
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
      if (cuenta.enviadas || cuenta.errores) {
        await this.db.registrar({
          usuario_id: usuario,
          fecha: new Date().toISOString(),
          ...cuenta,
          detalle: this.ultimoError() || 'Sincronización completada.',
        });
      }
      this.sincronizando.set(false);
      await this.cargar();
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
      if (err.status === 0) return 'Sin conexión con el servidor: se reintentará.';
      if (err.status === 401) return 'Tu sesión venció: inicia sesión para terminar de sincronizar (tus operaciones siguen guardadas).';
      const detalle = (err.error as { detail?: unknown } | null)?.detail;
      if (typeof detalle === 'string') return detalle;
    }
    return 'No se pudo sincronizar: se reintentará.';
  }
}
