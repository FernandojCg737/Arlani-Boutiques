import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';

const STAFF_TIPOS = new Set(['administrador', 'encargado_sucursal', 'cajero']);

export interface Cliente {
  id: number;
  nombre: string;
  email: string;
  telefono: string | null;
  direccion: string | null;
  tipo: string;
  rol: string | null;
  permisos: string[];
  sucursal_id: number | null;
}

export interface PerfilUpdatePayload {
  nombre: string;
  telefono?: string | null;
  direccion?: string | null;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  usuario: Cliente;
}

export interface RegisterPayload {
  nombre: string;
  email: string;
  password: string;
  telefono?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

const TOKEN_KEY = 'atelieraranier_token';
const CLIENTE_KEY = 'atelieraranier_cliente';

@Injectable({ providedIn: 'root' })
export class Auth {
  private readonly http = inject(HttpClient);

  readonly currentUser = signal<Cliente | null>(this.readCliente());
  readonly token = signal<string | null>(localStorage.getItem(TOKEN_KEY));
  readonly isAdmin = computed(() => this.currentUser()?.tipo === 'administrador');
  readonly isStaff = computed(() => STAFF_TIPOS.has(this.currentUser()?.tipo ?? ''));
  readonly sessionMessage = signal<string | null>(null);

  hasPermiso(codigo: string): boolean {
    return this.currentUser()?.permisos.includes(codigo) ?? false;
  }

  // Acciones de cliente (carrito, reservar, probador de RA): un visitante sin
  // sesion SI las ve -- al usarlas se le pide iniciar sesion (ver
  // LoginRequerido). Con sesion, se muestran solo si su rol tiene ese CU
  // habilitado (CU02, pestana Cliente).
  mostrarAccionCliente(codigo: string): boolean {
    if (!this.currentUser()) return true;
    return this.hasPermiso(codigo) || this.isAdmin();
  }

  // A donde mandar al usuario justo despues de iniciar sesion. Quien tiene
  // permiso de Bitacora (CU17) - tipicamente el Administrador - cae directo
  // ahi; el resto del personal cae en la landing del panel (accesos rapidos
  // segun su rol), y un Cliente va al inicio de la tienda.
  landingRoute(): string {
    if (this.hasPermiso('CU17')) return '/admin/bitacora';
    if (this.isStaff()) return '/admin';
    return '/';
  }

  async register(payload: RegisterPayload): Promise<Cliente> {
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiUrl}/auth/register`, payload),
    );
    this.persistSession(res);
    return res.usuario;
  }

  async login(payload: LoginPayload): Promise<Cliente> {
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiUrl}/auth/login`, payload),
    );
    this.persistSession(res);
    return res.usuario;
  }

  async loginWithGoogle(credential: string): Promise<Cliente> {
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiUrl}/auth/google`, { credential }),
    );
    this.persistSession(res);
    return res.usuario;
  }

  async forgotPassword(email: string): Promise<void> {
    await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/forgot-password`, { email }));
  }

  async verifyResetCode(email: string, code: string): Promise<string> {
    const res = await firstValueFrom(
      this.http.post<{ reset_token: string }>(`${environment.apiUrl}/auth/verify-reset-code`, { email, code }),
    );
    return res.reset_token;
  }

  async resetPassword(resetToken: string, newPassword: string): Promise<Cliente> {
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiUrl}/auth/reset-password`, {
        reset_token: resetToken,
        new_password: newPassword,
      }),
    );
    this.persistSession(res);
    return res.usuario;
  }

  async loginWithResetCode(resetToken: string): Promise<Cliente> {
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiUrl}/auth/login-with-reset-code`, {
        reset_token: resetToken,
      }),
    );
    this.persistSession(res);
    return res.usuario;
  }

  async updateProfile(payload: PerfilUpdatePayload): Promise<Cliente> {
    const res = await firstValueFrom(this.http.put<Cliente>(`${environment.apiUrl}/perfil`, payload));
    this.currentUser.set(res);
    try {
      localStorage.setItem(CLIENTE_KEY, JSON.stringify(res));
    } catch {
      // localStorage no disponible; la sesion sigue viva en memoria.
    }
    return res;
  }

  async changePassword(passwordActual: string, passwordNueva: string): Promise<Cliente> {
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiUrl}/perfil/cambiar-password`, {
        password_actual: passwordActual,
        password_nueva: passwordNueva,
      }),
    );
    this.persistSession(res);
    return res.usuario;
  }

  // Revalida la sesion contra el backend: si el token expiro, la cuenta se
  // desactivo, o se abrio sesion en otro dispositivo, esto lanza 401 y el
  // interceptor se encarga de cerrar la sesion local.
  async me(): Promise<Cliente> {
    const res = await firstValueFrom(this.http.get<Cliente>(`${environment.apiUrl}/auth/me`));
    this.currentUser.set(res);
    try {
      localStorage.setItem(CLIENTE_KEY, JSON.stringify(res));
    } catch {
      // localStorage no disponible; la sesion sigue viva en memoria.
    }
    return res;
  }

  async logout(): Promise<void> {
    try {
      if (this.token()) {
        await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/logout`, {}));
      }
    } catch {
      // best-effort: si el server no responde, igual limpiamos la sesion local.
    } finally {
      this.clearSession();
    }
  }

  // Usado por el interceptor HTTP cuando el backend rechaza el token (sesion
  // abierta en otro dispositivo, expirada, o cuenta desactivada).
  forceLogout(message: string): void {
    this.clearSession();
    this.sessionMessage.set(message);
  }

  private clearSession(): void {
    this.currentUser.set(null);
    this.token.set(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(CLIENTE_KEY);
  }

  private persistSession(res: TokenResponse): void {
    this.currentUser.set(res.usuario);
    this.token.set(res.access_token);
    try {
      localStorage.setItem(TOKEN_KEY, res.access_token);
      localStorage.setItem(CLIENTE_KEY, JSON.stringify(res.usuario));
    } catch {
      // localStorage no disponible; la sesion sigue viva en memoria.
    }
  }

  private readCliente(): Cliente | null {
    try {
      const raw = localStorage.getItem(CLIENTE_KEY);
      return raw ? (JSON.parse(raw) as Cliente) : null;
    } catch {
      return null;
    }
  }
}
