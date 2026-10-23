import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { CanMatchFn, Route, UrlMatchResult, UrlSegment } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

export interface SucursalPublica {
  nombre: string;
  direccion: string;
  ciudad: string;
  horario_atencion: string | null;
  telefono: string | null;
}

// Una tienda activa en la lista publica (GET /tiendas).
export interface TiendaResumen {
  id: number;
  nombre: string;
  subdominio: string;
  ciudad: string | null;
  color_marca: string;
  logo_url: string | null;
}

export interface TiendaPublica {
  id: number;
  nombre: string;
  subdominio: string;
  ciudad: string | null;
  color_marca: string;
  logo_url: string | null;
  // 'vencida': la suscripcion de la tienda vencio (no vende, igual que suspendida).
  estado: 'activa' | 'suspendida' | 'vencida';
  tiene_catalogo: boolean;
  // La tienda original tiene su sitio completo; las demas muestran su
  // catalogo dentro de su pagina.
  sitio_propio: boolean;
  sucursales: SucursalPublica[];
}

// Un minuto alcanza para que el guard y la pagina no pidan dos veces lo mismo,
// y si la tienda cambia (suspendida, catalogo nuevo) se ve enseguida.
const VIGENCIA_MS = 60_000;

// Datos publicos de cada tienda (GET /tiendas/{subdominio}). null = no existe.
@Injectable({ providedIn: 'root' })
export class TiendaPublicaApi {
  private readonly http = inject(HttpClient);
  private readonly cache = new Map<string, { hasta: number; tienda: Promise<TiendaPublica | null> }>();

  // Tiendas activas, en el orden en que se sumaron (carrusel de la portada).
  listar(): Promise<TiendaResumen[]> {
    return firstValueFrom(this.http.get<TiendaResumen[]>(`${environment.apiUrl}/tiendas`));
  }

  obtener(subdominio: string): Promise<TiendaPublica | null> {
    const guardada = this.cache.get(subdominio);
    if (guardada && guardada.hasta > Date.now()) return guardada.tienda;

    const tienda = firstValueFrom(
      this.http.get<TiendaPublica>(`${environment.apiUrl}/tiendas/${encodeURIComponent(subdominio)}`),
    ).catch((err) => {
      // "No existe" tambien se guarda; un error de red no, para reintentar.
      if (err?.status === 404) return null;
      this.cache.delete(subdominio);
      throw err;
    });
    this.cache.set(subdominio, { hasta: Date.now() + VIGENCIA_MS, tienda });
    return tienda;
  }
}

// Enlace de cada tienda: /tienda-<subdominio> (ej. /tienda-atelier-aranier).
// Va por ruta, no por subdominio, asi funciona en Render sin dominio propio.
export function tiendaMatcher(segmentos: UrlSegment[]): UrlMatchResult | null {
  const coincide = segmentos.length === 1 ? /^tienda-([a-z0-9][a-z0-9-]{1,38}[a-z0-9])$/.exec(segmentos[0].path) : null;
  if (!coincide) return null;
  return { consumed: segmentos, posParams: { subdominio: new UrlSegment(coincide[1], {}) } };
}

// Toda boutique activa usa la pagina de tienda (su logo, su color, portada con
// video y catalogo); una suspendida o inexistente, la ficha de la plataforma.
export const tieneCatalogoGuard: CanMatchFn = async (_route: Route, segmentos: UrlSegment[]) => {
  const subdominio = tiendaMatcher(segmentos)?.posParams?.['subdominio']?.path;
  if (!subdominio) return false;
  try {
    const tienda = await inject(TiendaPublicaApi).obtener(subdominio);
    return !!tienda && tienda.estado === 'activa';
  } catch {
    return false;
  }
};
