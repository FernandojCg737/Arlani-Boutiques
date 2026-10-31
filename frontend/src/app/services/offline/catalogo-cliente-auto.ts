import { HttpClient } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Auth } from '../auth';
import { ImagenesOffline } from './imagenes-offline';
import { CatalogoCliente, OfflineDb, OperacionLocal } from './offline-db';
import { Sincronizacion } from './sincronizacion';

const CADA_MS = 3_000;
const POR_ENVIAR = ['pendiente', 'enviando', 'error'];

// CU11 automático para el cliente: apenas entra a su perfil se descarga el
// catálogo sin conexión (las tiendas con plan Básico o Profesional, con su
// stock por sucursal, precios y fotos) y desde ahí, cada 3 segundos mientras
// tenga internet y la pestaña esté a la vista, se pregunta al servidor si algo
// cambió (una huella de pocos bytes). Solo si cambió se vuelve a descargar.
// Sigue activo en toda la app hasta que cierre sesión.
@Injectable({ providedIn: 'root' })
export class CatalogoClienteAuto {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly db = inject(OfflineDb);
  private readonly sync = inject(Sincronizacion);
  private readonly imagenes = inject(ImagenesOffline);
  private readonly api = `${environment.apiUrl}/offline/catalogo-cliente`;

  readonly catalogo = signal<CatalogoCliente | null>(null);
  readonly ultima = signal<string | null>(null);
  readonly descargando = signal(false);
  // Última vez que se confirmó con el servidor que el stock está al día.
  readonly revisadoEn = signal<Date | null>(null);

  private version: string | null = null;
  private reloj: ReturnType<typeof setInterval> | null = null;
  private usuarioId: number | null = null;
  // Se pidió iniciar (perfil o "Sin conexión"), aunque la sesión aún cargaba.
  private pedido = false;

  constructor() {
    const cliente = computed(() => {
      const u = this.auth.currentUser();
      return u?.tipo === 'cliente' ? u.id : null;
    });
    // El cliente de ahora se fija YA (no en el effect, que corre después de
    // iniciar() y antes detenía el reloj recién creado).
    this.usuarioId = untracked(cliente);
    if (this.usuarioId !== null) void this.leerGuardado(this.usuarioId);
    // Al cambiar quién inició sesión: lo guardado de ese cliente, o nada.
    effect(() => {
      const id = cliente();
      if (id === this.usuarioId) return;
      untracked(() => {
        // Se pidió iniciar mientras la sesión todavía cargaba: arranca ahora.
        const esperaba = this.pedido && this.usuarioId === null;
        this.detener();
        this.usuarioId = id;
        this.version = null;
        this.catalogo.set(null);
        if (id !== null) void this.leerGuardado(id);
        if (id !== null && esperaba) this.iniciar();
      });
    });
    window.addEventListener('online', () => void this.revisar());
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') void this.revisar();
    });
  }

  // Se llama al entrar al perfil (y en "Sin conexión").
  iniciar(): void {
    this.pedido = true;
    // Los permisos pueden llegar después: revisar() los vuelve a mirar en cada vuelta.
    if (this.reloj || this.auth.currentUser()?.tipo !== 'cliente') return;
    this.reloj = setInterval(() => void this.revisar(), CADA_MS);
    void this.revisar();
  }

  detener(): void {
    if (this.reloj) clearInterval(this.reloj);
    this.reloj = null;
    this.pedido = false;
  }

  // forzar: el botón "Actualizar catálogo" (descarga aunque no haya cambios y
  // propaga el error para mostrarlo).
  async revisar(forzar = false): Promise<void> {
    const u = this.auth.currentUser();
    if (!this.puede() || !u || this.descargando() || !navigator.onLine) return;
    if (!forzar && (!this.reloj || document.visibilityState !== 'visible')) return;
    this.descargando.set(true);
    try {
      const { version } = await firstValueFrom(this.http.get<{ version: string }>(`${this.api}/version`));
      this.revisadoEn.set(new Date());
      if (!forzar && version === this.version && this.catalogo()) return;
      const c = await firstValueFrom(
        this.http.get<CatalogoCliente>(this.api, { params: { automatica: !forzar } }),
      );
      if (this.usuarioId !== u.id) return;
      // Lo reservado o comprado que todavía no llegó al servidor sigue descontado.
      const pendientes = (await this.db.operaciones(u.id)).filter((o) => POR_ENVIAR.includes(o.estado));
      const catalogo = this.descontar(c, pendientes);
      await this.db.guardarPaquete({ clave: this.clave(u.id), usuario_id: u.id, descargado_en: c.descargado_en, datos: catalogo });
      this.version = version;
      this.catalogo.set(catalogo);
      this.ultima.set(new Date().toISOString());
      // Las fotos nuevas se bajan aparte (las ya guardadas se omiten).
      void this.imagenes.descargar(this.urls(catalogo)).then(() => this.imagenes.cargar(this.urls(catalogo)));
    } catch (err) {
      // Sin respuesta: se vuelve a intentar en la próxima vuelta.
      if (forzar) throw err;
    } finally {
      this.descargando.set(false);
    }
  }

  urls(c: CatalogoCliente): (string | null)[] {
    return c.tiendas.flatMap((t) => t.productos.map((p) => p.imagen_url));
  }

  private puede(): boolean {
    return this.auth.currentUser()?.tipo === 'cliente' && this.auth.hasPermiso('CU10');
  }

  private clave(usuarioId: number): string {
    return `cliente:${usuarioId}`;
  }

  private async leerGuardado(id: number): Promise<void> {
    const guardado = await this.db.paquete(this.clave(id));
    if (guardado && this.usuarioId === id && !this.catalogo()) this.catalogo.set(guardado.datos as CatalogoCliente);
  }

  private descontar(c: CatalogoCliente, ops: OperacionLocal[]): CatalogoCliente {
    if (!ops.length) return c;
    const usados = new Map<string, number>();
    for (const o of ops) {
      for (const i of o.items) {
        const k = `${i.producto_id}-${i.talla_id}-${i.color_id}-${o.sucursal_id}`;
        usados.set(k, (usados.get(k) ?? 0) + i.cantidad);
      }
    }
    return {
      ...c,
      tiendas: c.tiendas.map((t) => ({
        ...t,
        productos: t.productos.map((p) => ({
          ...p,
          variantes: p.variantes.map((v) => {
            const usado = usados.get(`${p.producto_id}-${v.talla_id}-${v.color_id}-${v.sucursal_id}`) ?? 0;
            return usado ? { ...v, stock: Math.max(0, v.stock - usado) } : v;
          }),
        })),
      })),
    };
  }
}
