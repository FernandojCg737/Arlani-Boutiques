import { Injectable, effect, inject } from '@angular/core';
import { Router } from '@angular/router';
import { Auth } from './auth';

const INACTIVITY_LIMIT_MS = 30 * 60 * 1000;
const HEARTBEAT_INTERVAL_MS = 3 * 1000;
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'] as const;

// Se instancia una sola vez desde App y vigila la sesion mientras haya un
// usuario logueado: cierra sesion sola a los 30 min sin actividad, y hace un
// heartbeat periodico contra /auth/me para detectar si la sesion se invalido
// (por ejemplo, porque se inicio sesion en otro dispositivo).
@Injectable({ providedIn: 'root' })
export class InactivitySession {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);

  private inactivityTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private listenersAttached = false;
  private readonly boundReset = () => this.resetInactivityTimer();

  constructor() {
    effect(() => {
      if (this.auth.currentUser()) {
        this.start();
      } else {
        this.stop();
      }
    });
  }

  private start(): void {
    if (this.listenersAttached) return;
    this.listenersAttached = true;
    ACTIVITY_EVENTS.forEach((event) => document.addEventListener(event, this.boundReset, { passive: true }));
    this.resetInactivityTimer();
    this.heartbeatTimer = setInterval(() => this.checkSession(), HEARTBEAT_INTERVAL_MS);
  }

  private stop(): void {
    if (!this.listenersAttached) return;
    this.listenersAttached = false;
    ACTIVITY_EVENTS.forEach((event) => document.removeEventListener(event, this.boundReset));
    if (this.inactivityTimer) clearTimeout(this.inactivityTimer);
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.inactivityTimer = null;
    this.heartbeatTimer = null;
  }

  private resetInactivityTimer(): void {
    if (this.inactivityTimer) clearTimeout(this.inactivityTimer);
    this.inactivityTimer = setTimeout(() => this.onInactivityTimeout(), INACTIVITY_LIMIT_MS);
  }

  private async onInactivityTimeout(): Promise<void> {
    // Sin conexion no se cierra la sesion: el personal no podria volver a
    // entrar hasta tener internet y perderia el modo sin conexion.
    if (!navigator.onLine) {
      this.resetInactivityTimer();
      return;
    }
    await this.auth.logout();
    this.auth.sessionMessage.set('Tu sesion se cerro por inactividad.');
    this.router.navigateByUrl('/login');
  }

  private async checkSession(): Promise<void> {
    try {
      await this.auth.me();
    } catch {
      // el interceptor HTTP ya fuerza el logout y redirige si corresponde
    }
  }
}
