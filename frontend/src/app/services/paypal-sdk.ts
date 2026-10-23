import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';

declare global {
  interface Window {
    paypal?: unknown;
    __arlaniPaypal?: Record<string, AccionesPaypal>;
  }
}

export interface AccionesPaypal {
  crearOrden: () => Promise<string>;
  aprobar: (orderId: string) => Promise<void>;
  cancelar: () => void;
  error: (e: unknown) => void;
  altura: (px: number) => void;
}

// Carga el script del SDK de PayPal una sola vez (cachea la promesa: si se
// pide de nuevo mientras ya esta cargando, o ya cargado, reusa lo mismo en
// vez de inyectar el <script> dos veces).
@Injectable({ providedIn: 'root' })
export class PaypalSdk {
  private promesa: Promise<unknown> | null = null;

  // SDK de la plataforma Arlani (suscripciones, "Pagar todo").
  cargar(): Promise<unknown> {
    if (window.paypal) return Promise.resolve(window.paypal);
    if (this.promesa) return this.promesa;

    this.promesa = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      // enable-funding=card: sin esto, algunas cuentas de PayPal no muestran
      // el boton de tarjeta de invitado (depende de que funding tenga
      // habilitado esa cuenta) y solo se ve el boton de PayPal -- forzarlo
      // lo deja visible siempre que este disponible. locale=es_BO: sin esto
      // el texto del boton sale en ingles en vez de espanol.
      script.src = `https://www.paypal.com/sdk/js?client-id=${environment.paypalClientId}&currency=USD&intent=capture&enable-funding=card&locale=es_BO`;
      script.onload = () => resolve(window.paypal);
      script.onerror = () => reject(new Error('No se pudo cargar el SDK de PayPal.'));
      document.head.appendChild(script);
    });
    return this.promesa;
  }

  // Botones de PayPal de una TIENDA (cobra con su client-id). PayPal no deja
  // dos SDK con client-id distinto en la misma pagina, asi que cada tienda
  // los dibuja en su propio iframe (public/paypal-botones.html); las
  // acciones (crear y capturar la orden) las sigue haciendo esta pagina.
  // Devuelve la funcion para desmontarlos.
  montarBotones(contenedor: HTMLElement, clientId: string, acciones: Omit<AccionesPaypal, 'altura'>): () => void {
    const canal = `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
    const iframe = document.createElement('iframe');
    iframe.title = 'Pagar con PayPal';
    iframe.style.cssText = 'width:100%;height:160px;border:0;display:block;';
    window.__arlaniPaypal = window.__arlaniPaypal ?? {};
    window.__arlaniPaypal[canal] = { ...acciones, altura: (px) => (iframe.style.height = `${Math.max(px, 50)}px`) };
    iframe.src = `/paypal-botones.html?client-id=${encodeURIComponent(clientId)}&canal=${canal}`;
    contenedor.innerHTML = '';
    contenedor.appendChild(iframe);
    return () => {
      iframe.remove();
      delete window.__arlaniPaypal?.[canal];
    };
  }
}
