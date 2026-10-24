import { HttpClient } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { Auth } from './auth';
import { TiendaActiva } from './tienda-activa';

export interface MensajeChat {
  id: number;
  remitente: 'cliente' | 'bot';
  mensaje: string;
  fecha: string;
  // CU18: lo que el modelo de la tienda entendió (solo mensajes del cliente).
  intencion?: string | null;
  confianza?: number | null;
}

// CU19: historial de la conversacion del cliente con el chatbot de la
// tienda que esta visitando -- el backend arma la respuesta (modelo de la
// tienda + sus datos, Gemini de respaldo), aca solo se manda el mensaje y se
// muestra lo que vuelve. En la portada y el catalogo de Arlani, quien no
// tiene sesion de cliente (p. ej. un dueno de boutique que mira los planes)
// usa el asistente publico: la conversacion queda solo en este navegador.
const CLAVE_PUBLICA = 'arlani_chat_universal';

function leerPublica(): MensajeChat[] {
  try {
    return JSON.parse(sessionStorage.getItem(CLAVE_PUBLICA) ?? '[]');
  } catch {
    return [];
  }
}

function guardarPublica(mensajes: MensajeChat[]): void {
  try {
    sessionStorage.setItem(CLAVE_PUBLICA, JSON.stringify(mensajes.slice(-40)));
  } catch {
    // Sin sessionStorage el chat sigue andando, solo no sobrevive a recargar.
  }
}

@Injectable({ providedIn: 'root' })
export class ChatbotService {
  private readonly http = inject(HttpClient);
  private readonly tiendaActiva = inject(TiendaActiva);
  private readonly auth = inject(Auth);
  // El chat del catálogo universal (todas las tiendas); lo fija el widget.
  readonly universal = signal(false);
  // Universal sin sesión de cliente: el asistente público (sin historial en el servidor).
  readonly publico = computed(() => this.universal() && this.auth.currentUser()?.tipo !== 'cliente');
  // Chat de la conversacion cargada: '*' universal, '' la tienda por
  // defecto, o el subdominio (undefined: todavia ninguna).
  private claveCargada: string | undefined;

  constructor() {
    // Cada tienda (y el universal) tiene su propio chat: al pasar a otro, se trae el suyo.
    effect(() => {
      const sub = this.tiendaActiva.subdominio();
      const clave = this.clave;
      untracked(() => {
        if ((sub !== undefined || this.universal()) && this.claveCargada !== undefined && clave !== this.claveCargada) {
          void this.cargar();
        }
      });
    });
  }

  private get clave(): string {
    if (this.universal()) return this.publico() ? 'publico' : '*';
    return this.tiendaActiva.subdominio() ?? '';
  }

  // Lo que va al backend para saber de qué chat se trata.
  private alcance(clave: string): { tienda: string | null; universal: boolean } {
    return { tienda: clave && clave !== '*' && clave !== 'publico' ? clave : null, universal: clave === '*' };
  }

  private readonly _mensajes = signal<MensajeChat[]>([]);
  readonly mensajes = this._mensajes.asReadonly();
  readonly enviando = signal(false);

  async cargar(): Promise<void> {
    const clave = this.clave;
    this.claveCargada = clave;
    if (clave === 'publico') {
      this._mensajes.set(leerPublica());
      return;
    }
    try {
      const { tienda, universal } = this.alcance(clave);
      const params: Record<string, string> = universal ? { universal: 'true' } : tienda ? { tienda } : {};
      const res = await firstValueFrom(this.http.get<MensajeChat[]>(`${environment.apiUrl}/chatbot/mias`, { params }));
      if (this.clave === clave) this._mensajes.set(res);
    } catch {
      this._mensajes.set([]);
    }
  }

  async enviar(mensaje: string): Promise<MensajeChat | null> {
    const texto = mensaje.trim();
    if (!texto) return null;

    const optimista: MensajeChat = {
      id: -Date.now(),
      remitente: 'cliente',
      mensaje: texto,
      fecha: new Date().toISOString(),
    };
    this._mensajes.update((m) => [...m, optimista]);

    this.enviando.set(true);
    try {
      const res = this.publico() ? await this.enviarPublico(texto) : await firstValueFrom(
        this.http.post<MensajeChat>(`${environment.apiUrl}/chatbot/mensajes`, { mensaje: texto, ...this.alcance(this.clave) }),
      );
      this._mensajes.update((m) => [...m, res]);
      if (this.publico()) guardarPublica(this._mensajes());
      return res;
    } catch {
      this._mensajes.update((m) => [
        ...m,
        {
          id: -Date.now(),
          remitente: 'bot',
          mensaje: 'No pudimos conectar con el asistente. Intenta de nuevo en un momento.',
          fecha: new Date().toISOString(),
        },
      ]);
      return null;
    } finally {
      this.enviando.set(false);
    }
  }

  private async enviarPublico(texto: string): Promise<MensajeChat> {
    // Los mensajes anteriores van como historial (el servidor no los guarda).
    const historial = this._mensajes()
      .slice(0, -1)
      .filter((m) => m.id > 0 || m.remitente === 'cliente')
      .slice(-10)
      .map((m) => ({ remitente: m.remitente, mensaje: m.mensaje }));
    const r = await firstValueFrom(
      this.http.post<{ mensaje: string }>(`${environment.apiUrl}/chatbot/publico`, { mensaje: texto, historial }),
    );
    return { id: Date.now(), remitente: 'bot', mensaje: r.mensaje, fecha: new Date().toISOString() };
  }

  limpiarLocal(): void {
    this.claveCargada = undefined;
    this._mensajes.set([]);
  }
}
