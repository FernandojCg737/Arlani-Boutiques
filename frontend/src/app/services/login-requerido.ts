import { Injectable, signal } from '@angular/core';

export interface PedidoLogin {
  // Que queria hacer el visitante, para armar el mensaje ("para anadir al
  // carrito", "para reservar", ...).
  accion: string;
  // A donde volver despues de iniciar sesion / registrarse (ruta interna).
  returnUrl: string;
}

// Aviso global de "inicia sesion para continuar": carrito, reservas y el
// probador de RA se muestran tambien a visitantes sin sesion, pero al
// usarlos se les pide iniciar sesion (o crear una cuenta) en vez de
// ocultarles la funcionalidad. El modal vive una sola vez en app.html.
@Injectable({ providedIn: 'root' })
export class LoginRequerido {
  readonly pedido = signal<PedidoLogin | null>(null);

  pedir(accion: string, returnUrl: string): void {
    this.pedido.set({ accion, returnUrl });
  }

  cerrar(): void {
    this.pedido.set(null);
  }
}

// Solo rutas internas: evita que un `returnUrl` manipulado (ej.
// "//sitio-malicioso.com") saque al usuario del sitio despues del login.
export function esRutaInterna(url: string | null | undefined): url is string {
  return !!url && url.startsWith('/') && !url.startsWith('//') && !url.startsWith('/\\');
}
