import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

// CU22 Live commerce: tipos y llamadas a /live (el video va por LiveKit).

export interface LiveResumen {
  id: number;
  empresa_id: number;
  tienda: string;
  subdominio: string;
  logo_url: string | null;
  color_marca: string | null;
  titulo: string;
  descripcion: string | null;
  estado: 'en_vivo' | 'finalizado' | 'cortado';
  inicio: string;
  fin: string | null;
  espectadores: number;
  espectadores_max: number;
  comentarios: number;
  iniciado_por: string | null;
  grabacion_estado: 'pendiente' | 'grabando' | 'procesando' | 'lista' | 'fallida' | 'borrada';
  grabacion_segundos: number | null;
  grabacion_bytes: number | null;
  grabacion_error: string | null;
  grabacion_inicio: string | null;
  motivo_corte: string | null;
  cortado_por: string | null;
}

export interface VarianteLive {
  talla_id: number;
  talla: string;
  color_id: number;
  color: string;
  sucursal_id: number;
  sucursal: string;
  stock: number;
}

export interface ProductoLive {
  id: number;
  nombre: string;
  precio: number;
  precio_original: number | null;
  imagen: string | null;
  fijado: boolean;
  variantes: VarianteLive[];
}

export interface ComentarioLive {
  id: number;
  usuario_id: number;
  usuario: string;
  foto_url: string | null;
  texto: string;
  fecha: string;
  oculto: boolean;
  es_tienda: boolean;
}

// Comentario con su segundo en la grabación (repetición con chat).
export interface ComentarioRepeticion extends ComentarioLive {
  segundo: number;
}

export interface EspectadorLive {
  usuario_id: number;
  nombre: string;
  foto_url: string | null;
  entro_en: string;
  conectado: boolean;
  comentarios: number;
  bloqueo: 'silenciado' | 'expulsado' | null;
}

export interface SalaLive {
  live: LiveResumen;
  url: string;
  token: string;
  vendedor: boolean;
  moderador: boolean;
  silenciado: boolean;
  productos: ProductoLive[];
  comentarios: ComentarioLive[];
  espectadores: EspectadorLive[] | null;
}

// Mensajes que el backend reparte a la sala (tema "live").
export type MensajeLive =
  | { tipo: 'comentario'; comentario: ComentarioLive }
  | { tipo: 'ocultar'; id: number }
  | { tipo: 'productos'; productos: ProductoLive[] }
  | { tipo: 'reaccion'; emoji: string; usuario_id: number }
  | { tipo: 'bloqueo'; usuario_id: number; bloqueo: 'silenciado' | 'expulsado' | null }
  | { tipo: 'fin'; motivo: string | null };

export const EMOJIS_LIVE = ['❤️', '🔥', '😍', '👏', '😂', '🛍️'];

// Las fechas del backend vienen en UTC sin zona.
export function fechaUtc(fecha: string | null): string | null {
  if (!fecha) return null;
  return /[zZ]|[+-]\d\d:?\d\d$/.test(fecha) ? fecha : fecha + 'Z';
}

@Injectable({ providedIn: 'root' })
export class LiveApi {
  private readonly http = inject(HttpClient);
  private readonly api = `${environment.apiUrl}/live`;

  // Lives en curso (el punto rojo del botón LIVE de la portada).
  readonly enVivo = signal<LiveResumen[]>([]);

  async revisarEnVivo(): Promise<LiveResumen[]> {
    try {
      const lista = await firstValueFrom(this.http.get<LiveResumen[]>(`${this.api}/en-vivo`));
      this.enVivo.set(lista);
      return lista;
    } catch {
      return this.enVivo();
    }
  }

  sala(id: number): Promise<SalaLive> {
    return firstValueFrom(this.http.get<SalaLive>(`${this.api}/${id}/sala`));
  }

  comentar(id: number, texto: string): Promise<ComentarioLive> {
    return firstValueFrom(this.http.post<ComentarioLive>(`${this.api}/${id}/comentarios`, { texto }));
  }

  reaccionar(id: number, emoji: string): Promise<unknown> {
    return firstValueFrom(this.http.post(`${this.api}/${id}/reacciones`, { emoji }));
  }

  // ---------------------------------------------------------------- tienda

  estadoTienda(empresaId?: number | null): Promise<{ disponible: boolean; configurado: boolean; plan: string | null; actual: LiveResumen | null }> {
    const params: Record<string, string> = empresaId ? { empresa_id: String(empresaId) } : {};
    return firstValueFrom(this.http.get<any>(`${this.api}/tienda/estado`, { params }));
  }

  productosTienda(): Promise<{ id: number; nombre: string; precio: number; imagen: string | null; stock: number }[]> {
    return firstValueFrom(this.http.get<any[]>(`${this.api}/tienda/productos`));
  }

  iniciar(titulo: string, descripcion: string, productoIds: number[]): Promise<SalaLive> {
    return firstValueFrom(
      this.http.post<SalaLive>(`${this.api}/tienda`, { titulo, descripcion: descripcion || null, producto_ids: productoIds }),
    );
  }

  historial(empresaId?: number | null): Promise<LiveResumen[]> {
    const params: Record<string, string> = empresaId ? { empresa_id: String(empresaId) } : {};
    return firstValueFrom(this.http.get<LiveResumen[]>(`${this.api}/tienda/historial`, { params }));
  }

  grabar(id: number): Promise<LiveResumen> {
    return firstValueFrom(this.http.post<LiveResumen>(`${this.api}/${id}/grabar`, {}));
  }

  finalizar(id: number): Promise<LiveResumen> {
    return firstValueFrom(this.http.post<LiveResumen>(`${this.api}/${id}/finalizar`, {}));
  }

  fijar(id: number, productoId: number | null): Promise<ProductoLive[]> {
    return firstValueFrom(this.http.put<ProductoLive[]>(`${this.api}/${id}/fijado`, { producto_id: productoId }));
  }

  agregarProducto(id: number, productoId: number): Promise<ProductoLive[]> {
    return firstValueFrom(this.http.post<ProductoLive[]>(`${this.api}/${id}/productos`, { producto_id: productoId }));
  }

  ocultar(id: number, comentarioId: number): Promise<unknown> {
    return firstValueFrom(this.http.post(`${this.api}/${id}/comentarios/${comentarioId}/ocultar`, {}));
  }

  espectadores(id: number): Promise<EspectadorLive[]> {
    return firstValueFrom(this.http.get<EspectadorLive[]>(`${this.api}/${id}/espectadores`));
  }

  bloquear(id: number, usuarioId: number, tipo: 'silenciado' | 'expulsado'): Promise<EspectadorLive[]> {
    return firstValueFrom(this.http.post<EspectadorLive[]>(`${this.api}/${id}/bloqueos`, { usuario_id: usuarioId, tipo }));
  }

  desbloquear(id: number, usuarioId: number): Promise<EspectadorLive[]> {
    return firstValueFrom(this.http.delete<EspectadorLive[]>(`${this.api}/${id}/bloqueos/${usuarioId}`));
  }

  grabacion(id: number): Promise<{ url: string }> {
    return firstValueFrom(this.http.get<{ url: string }>(`${this.api}/${id}/grabacion`));
  }

  comentariosDelLive(id: number): Promise<ComentarioRepeticion[]> {
    return firstValueFrom(this.http.get<ComentarioRepeticion[]>(`${this.api}/${id}/comentarios`));
  }

  borrarGrabacion(id: number): Promise<LiveResumen> {
    return firstValueFrom(this.http.delete<LiveResumen>(`${this.api}/${id}/grabacion`));
  }

  cortar(id: number, motivo: string): Promise<LiveResumen> {
    return firstValueFrom(this.http.post<LiveResumen>(`${this.api}/${id}/cortar`, { motivo }));
  }
}
