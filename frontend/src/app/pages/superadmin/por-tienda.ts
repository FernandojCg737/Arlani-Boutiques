import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';
import { PARCIALES, ubicarRuta } from './superadmin-menu';

// CUs del 2do parcial que el SuperAdministrador trabaja dentro de una tienda
// (CU03 sucursales, CU04 catálogo e inventario): primero elige la tienda y
// la pantalla queda limitada a ella (?empresa=<id> en la URL, que el
// interceptor manda al backend como X-Empresa).
export const RUTAS_POR_TIENDA = new Set(
  PARCIALES.find((p) => p.id === 'p2')!
    .paquetes.flatMap((pk) => pk.casos)
    .filter((c) => c.porEmpresa)
    .flatMap((c) => [c.ruta, ...(c.subs ?? []).map((s) => s.ruta)])
    .filter((r): r is string => !!r),
);

// Tienda elegida en una URL del panel (/superadmin/<ruta>?empresa=<id>), o
// null si la pantalla no es por tienda.
export function tiendaDeUrl(url: UrlTree): number | null {
  const segs = url.root.children['primary']?.segments.map((s) => s.path) ?? [];
  if (segs[0] !== 'superadmin' || !RUTAS_POR_TIENDA.has(segs.slice(1).join('/'))) return null;
  const id = Number(url.queryParamMap.get('empresa'));
  return Number.isInteger(id) && id > 0 ? id : null;
}

// Sin tienda elegida, manda a elegirla (y vuelve a esta misma pantalla).
export const tiendaElegidaGuard: CanActivateFn = (route) => {
  const id = Number(route.queryParamMap.get('empresa'));
  if (Number.isInteger(id) && id > 0) return true;
  const ruta = route.routeConfig?.path ?? '';
  const codigo = ubicarRuta(ruta)?.caso.codigo ?? '';
  return inject(Router).createUrlTree(['/superadmin/tiendas', codigo], { queryParams: { destino: ruta } });
};
