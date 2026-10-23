import { HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Auth } from '../services/auth';

// Revalida contra el backend en cada navegacion: si el usuario cerro sesion
// (o su sesion quedo invalidada), no puede volver a entrar con el "back" del
// navegador ni con datos viejos en localStorage.
//
// Manda a /login con `returnUrl` (la pagina a la que queria entrar) para que
// login.ts pueda volver ahi despues -- antes mandaba siempre a home/landing
// y se perdia adonde iba el cliente (reportado por testers: entraba a
// Checkout sin sesion, iniciaba sesion, y terminaba en el inicio en vez de
// seguir con su compra).
// Sin conexion (P4 offline) el backend no responde: se sigue con la sesion
// guardada en el dispositivo; se revalida al volver la conexion.
function sinConexion(err: unknown, auth: Auth): boolean {
  return err instanceof HttpErrorResponse && err.status === 0 && auth.currentUser() !== null;
}

export const authGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(Auth);
  const router = inject(Router);

  if (!auth.token()) return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });

  try {
    await auth.me();
    return true;
  } catch (err) {
    if (sinConexion(err, auth)) return true;
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }
};

// Protege el shell del panel: cualquier tipo de personal (administrador,
// encargado de sucursal, cajero) puede entrar. Que CUs ve dentro ya lo filtra
// el sidebar segun sus permisos (CU02), y cada endpoint lo vuelve a validar.
export const adminGuard: CanActivateFn = async () => {
  const auth = inject(Auth);
  const router = inject(Router);

  if (!auth.token()) return router.createUrlTree(['/login']);

  try {
    await auth.me();
  } catch (err) {
    if (!sinConexion(err, auth)) return router.createUrlTree(['/login']);
  }

  return auth.isStaff() ? true : router.createUrlTree(['/']);
};

// Defensa adicional por ruta: si el rol del usuario no tiene el permiso de
// ese CU especifico, lo saca del panel en vez de dejarlo ver una pantalla
// rota por los 403 del backend.
export const permisoGuard = (codigo: string): CanActivateFn => {
  return () => {
    const auth = inject(Auth);
    const router = inject(Router);
    return auth.hasPermiso(codigo) || auth.isAdmin() ? true : router.createUrlTree(['/admin']);
  };
};

// Pantallas del Administrador de una tienda (ej. Mi suscripcion): el
// personal de la tienda y el SuperAdministrador (sin tienda) vuelven al panel.
export const adminTiendaGuard: CanActivateFn = () => {
  const auth = inject(Auth);
  const router = inject(Router);
  return auth.isAdmin() && !auth.isSuperAdmin() ? true : router.createUrlTree(['/admin']);
};

// Igual que permisoGuard pero para paginas del lado del cliente (carrito,
// reservas, etc.): si HAY sesion y el rol Cliente no tiene ese CU habilitado
// (CU02), manda al inicio. A un visitante sin sesion no lo bloquea aca --
// eso ya lo decide authGuard si la ruta tambien lo exige.
export const clientePermisoGuard = (codigo: string): CanActivateFn => {
  return () => {
    const auth = inject(Auth);
    const router = inject(Router);
    if (!auth.currentUser()) return true;
    return auth.hasPermiso(codigo) || auth.isAdmin() ? true : router.createUrlTree(['/']);
  };
};

// Panel de la plataforma (/superadmin): solo el SuperAdministrador. Igual que
// adminGuard, revalida la sesion contra el backend en cada navegacion.
export const superadminGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(Auth);
  const router = inject(Router);

  if (!auth.token()) return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });

  try {
    await auth.me();
  } catch {
    return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  }

  return auth.isSuperAdmin() ? true : router.createUrlTree([auth.landingRoute()]);
};
