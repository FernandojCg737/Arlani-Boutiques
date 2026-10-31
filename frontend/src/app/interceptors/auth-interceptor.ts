import { HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, tap, throwError } from 'rxjs';
import { tiendaDeUrl } from '../pages/superadmin/por-tienda';
import { Auth } from '../services/auth';
import { EstadoTienda } from '../services/estado-tienda';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(Auth);
  const router = inject(Router);
  const estadoTienda = inject(EstadoTienda);
  const token = auth.token();

  // CU17: le dice al backend de que app vino la accion (ver bitacora,
  // columna "plataforma") -- se manda siempre, no solo autenticado, para
  // que quede en acciones anonimas como registro/login tambien.
  const headers: Record<string, string> = { 'X-Client-Platform': 'web' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  // SuperAdministrador dentro de una tienda (CU03/CU04): el backend lo limita
  // a esa empresa. Durante una navegación vale la URL de destino, así las
  // peticiones de la pantalla que se está abriendo ya van con su tienda.
  if (token && auth.isSuperAdmin() && !req.url.includes('/plataforma/')) {
    const tienda = tiendaDeUrl(router.currentNavigation()?.finalUrl ?? router.parseUrl(router.url));
    if (tienda) headers['X-Empresa'] = String(tienda);
  }
  const authReq = req.clone({ setHeaders: headers });

  return next(authReq).pipe(
    // Sesión que se renueva sola mientras se usa: el backend manda el token
    // nuevo en X-Token-Renovado y vence recién tras días sin actividad.
    tap((evento) => {
      const nuevo = evento instanceof HttpResponse ? evento.headers.get('X-Token-Renovado') : null;
      if (nuevo && auth.token() === token) auth.renovarToken(nuevo);
    }),
    catchError((error: unknown) => {
      // Tienda con la suscripcion vencida: el panel se bloquea y el
      // Administrador va directo a renovarla.
      if (error instanceof HttpErrorResponse && error.status === 402 && error.headers.get('X-Suscripcion') === 'vencida') {
        estadoTienda.vencida.set(true);
        if (auth.currentUser()?.tipo === 'administrador' && !router.url.startsWith('/admin/suscripcion')) {
          void router.navigateByUrl('/admin/suscripcion');
        }
      }
      // Solo forzamos el logout si el request iba autenticado: un 401 en
      // /auth/login (contrasena incorrecta) es un error normal de formulario,
      // no una sesion invalidada.
      if (token && error instanceof HttpErrorResponse && error.status === 401) {
        const detail = (error.error as { detail?: unknown } | null)?.detail;
        const message = typeof detail === 'string' ? detail : 'Tu sesion expiro. Inicia sesion de nuevo.';
        auth.forceLogout(message);
        router.navigateByUrl('/login');
      }
      return throwError(() => error);
    }),
  );
};
