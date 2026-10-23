import { HttpClient } from '@angular/common/http';
import { Injectable, effect, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Auth } from '../auth';
import { ImagenesOffline } from './imagenes-offline';
import { OfflineDb, PaquetePersonal } from './offline-db';
import { Sincronizacion } from './sincronizacion';

const CADA_MS = 3 * 60_000;
const PERSONAL = new Set(['administrador', 'encargado_sucursal', 'cajero']);
const POR_ENVIAR = ['pendiente', 'enviando', 'error'];

export function clavePaquete(usuarioId: number, sucursalId: number): string {
  return `personal:${usuarioId}:${sucursalId}`;
}

// CU11 automático: mientras el personal de una tienda con plan Básico o
// Profesional tiene internet, el paquete de sus sucursales (productos,
// precios, stock, clientes y fotos) se descarga solo cada 3 minutos, en
// cualquier pantalla del panel. Si se corta la conexión de golpe ya lo tiene
// para seguir vendiendo en "Trabajar sin conexión". Al volver la conexión,
// PRIMERO se envían las ventas y reservas pendientes (CU12) y después se
// vuelve a descargar.
@Injectable({ providedIn: 'root' })
export class DescargaAutomatica {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly db = inject(OfflineDb);
  private readonly sync = inject(Sincronizacion);
  private readonly imagenes = inject(ImagenesOffline);

  // Cuándo terminó la última descarga automática (las pantallas se refrescan).
  readonly ultima = signal<string | null>(null);
  readonly descargando = signal(false);

  private planDe: number | null = null;
  private planOffline = false;

  constructor() {
    setInterval(() => void this.ejecutar(), CADA_MS);
    window.addEventListener('online', () => void this.ejecutar());
    effect(() => {
      const u = this.auth.currentUser();
      if (u && PERSONAL.has(u.tipo)) void this.ejecutar();
    });
  }

  async ejecutar(): Promise<void> {
    const u = this.auth.currentUser();
    if (!u || !PERSONAL.has(u.tipo) || this.descargando() || !navigator.onLine) return;
    if (!this.auth.isAdmin() && !this.auth.hasPermiso('2P-CU11')) return;
    this.descargando.set(true);
    try {
      // 1) Lo que se hizo sin conexión va primero.
      await this.sync.sincronizar();
      while (this.sync.sincronizando()) await new Promise((r) => setTimeout(r, 300));

      // 2) Solo tiendas cuyo plan incluye la operación sin conexión.
      if (this.planDe !== u.id) {
        const r = await firstValueFrom(this.http.get<{ offline: boolean }>(`${environment.apiUrl}/ventas/origenes`));
        this.planOffline = r.offline;
        this.planDe = u.id;
      }
      if (!this.planOffline) return;

      // 3) El paquete de cada sucursal donde puede vender (la suya, o todas el Administrador).
      const sucursales = await firstValueFrom(
        this.http.get<{ id: number; nombre: string }[]>(`${environment.apiUrl}/ventas/presencial/sucursales`),
      );
      const pendientes = (await this.db.operaciones(u.id)).filter((o) => POR_ENVIAR.includes(o.estado));
      for (const s of sucursales) {
        const datos = await firstValueFrom(
          this.http.get<PaquetePersonal>(`${environment.apiUrl}/offline/paquete`, {
            params: { sucursal_id: s.id, automatica: true },
          }),
        );
        // Lo vendido o reservado que todavía no llegó al servidor sigue descontado.
        const paquete = this.descontar(datos, pendientes.filter((o) => o.sucursal_id === s.id));
        await this.db.guardarPaquete({
          clave: clavePaquete(u.id, s.id),
          usuario_id: u.id,
          descargado_en: paquete.descargado_en,
          datos: paquete,
        });
        await this.imagenes.descargar(paquete.productos.map((p) => p.imagen_url));
      }
      this.ultima.set(new Date().toISOString());
    } catch {
      // Sin conexión o el servidor no respondió: se intenta en la próxima vuelta.
    } finally {
      this.descargando.set(false);
    }
  }

  private descontar(p: PaquetePersonal, ops: { items: { producto_id: number; talla_id: number; color_id: number; cantidad: number }[] }[]): PaquetePersonal {
    if (!ops.length) return p;
    const usados = new Map<string, number>();
    for (const o of ops) {
      for (const i of o.items) {
        const k = `${i.producto_id}-${i.talla_id}-${i.color_id}`;
        usados.set(k, (usados.get(k) ?? 0) + i.cantidad);
      }
    }
    return {
      ...p,
      productos: p.productos.map((prod) => ({
        ...prod,
        variantes: prod.variantes.map((v) => {
          const usado = usados.get(`${prod.producto_id}-${v.talla_id}-${v.color_id}`) ?? 0;
          return usado ? { ...v, stock: Math.max(0, v.stock - usado) } : v;
        }),
      })),
    };
  }
}
