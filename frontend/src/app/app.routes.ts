import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { AdminLayout } from './pages/admin/admin-layout/admin-layout';
import { AdminArUso } from './pages/admin/ar-uso/ar-uso';
import { AdminBitacora } from './pages/admin/bitacora/bitacora';
import { AdminCatalogo } from './pages/admin/catalogo/catalogo';
import { AdminClientes } from './pages/admin/clientes/clientes';
import { AdminHome } from './pages/admin/home/home';
import { AdminInventario } from './pages/admin/inventario/inventario';
import { AdminPerfil } from './pages/admin/perfil/perfil';
import { AdminProductos } from './pages/admin/productos/productos';
import { AdminCarritos } from './pages/admin/carritos/carritos';
import { AdminNotificaciones } from './pages/admin/notificaciones/notificaciones';
import { AdminReportesDashboard } from './pages/admin/reportes/dashboard/dashboard';
import { ReporteVentasPage } from './pages/admin/reportes/ventas/ventas';
import { ReporteAsistenciaPage } from './pages/admin/reportes/asistencia/asistencia';
import { ReporteInventarioPage } from './pages/admin/reportes/inventario/inventario';
import { ReporteReservasPage } from './pages/admin/reportes/reservas/reservas';
import { ReporteProductosPage } from './pages/admin/reportes/productos/productos';
import { AdminRecomendaciones } from './pages/admin/recomendaciones/recomendaciones';
import { AdminChatbot } from './pages/admin/chatbot/chatbot';
import { AdminChatbotDetalle } from './pages/admin/chatbot-detalle/chatbot-detalle';
import { AdminCalificaciones } from './pages/admin/calificaciones/calificaciones';
import { AdminReservas } from './pages/admin/reservas/reservas';
import { AdminProveedores } from './pages/admin/proveedores/proveedores';
import { AdminSesiones } from './pages/admin/sesiones/sesiones';
import { AdminTemporadas } from './pages/admin/temporadas/temporadas';
import { AdminSucursales } from './pages/admin/sucursales/sucursales';
import { AdminSuscripcion } from './pages/admin/suscripcion/suscripcion';
import { AdminFactura } from './pages/admin/factura/factura';
import { AdminUsuarios } from './pages/admin/usuarios/usuarios';
import { AdminVentas } from './pages/admin/ventas/ventas';
import { AtelierInicio } from './pages/atelier-inicio/atelier-inicio';
import { Carrito } from './pages/carrito/carrito';
import { Checkout } from './pages/checkout/checkout';
import { Comprobante } from './pages/comprobante/comprobante';
import { Cotizaciones } from './pages/cotizaciones/cotizaciones';
import { Home } from './pages/home/home';
import { Login } from './pages/login/login';
import { Perfil } from './pages/perfil/perfil';
import { ProductoDetalle } from './pages/producto-detalle/producto-detalle';
import { RecuperarPassword } from './pages/recuperar-password/recuperar-password';
import { Registro } from './pages/registro/registro';
import { RegistroEmpresa } from './pages/registro-empresa/registro-empresa';
import { Tienda } from './pages/tienda/tienda';
import { TiendaEmpresa } from './pages/tienda-empresa/tienda-empresa';
import { tieneCatalogoGuard, tiendaMatcher } from './services/tienda-publica';
import { adminGuard, adminTiendaGuard, authGuard, clientePermisoGuard, permisoGuard, superadminGuard } from './guards/auth-guard';
import { SuperadminEmpresas } from './pages/superadmin/empresas/empresas';
import { SuperadminElegirEmpresa } from './pages/superadmin/elegir-empresa/elegir-empresa';
import { SuperadminEnConstruccion } from './pages/superadmin/en-construccion/en-construccion';
import { SuperadminPlanes } from './pages/superadmin/planes/planes';
import { SuperadminLayout } from './pages/superadmin/superadmin-layout';

export const routes: Routes = [
  { path: '', component: Home, data: { header: 'plataforma' } },
  // Alta de una boutique nueva en la plataforma (viene desde Precios). Pide
  // sesión: sin sesión, authGuard manda a /login y vuelve acá con el plan.
  { path: 'empezar', component: RegistroEmpresa, canActivate: [authGuard], data: { hideChrome: true } },
  { path: 'atelier', component: AtelierInicio },
  // Enlace de cada tienda: /tienda-<subdominio>. Con catalogo muestra sus
  // productos; si todavia no tiene, su ficha (marca y sucursales).
  { matcher: tiendaMatcher, canMatch: [tieneCatalogoGuard], component: Tienda },
  {
    matcher: tiendaMatcher,
    component: TiendaEmpresa,
    data: { header: 'plataforma', encabezadoSolido: true },
  },
  // Direccion anterior del catalogo: sigue funcionando (con sus filtros).
  {
    path: 'tienda',
    pathMatch: 'full',
    redirectTo: ({ queryParams }) => inject(Router).createUrlTree(['/tienda-atelier-aranier'], { queryParams }),
  },
  { path: 'cotizaciones', component: Cotizaciones },
  // El carrito es de la plataforma (puede juntar prendas de varias boutiques).
  {
    path: 'carrito',
    component: Carrito,
    canActivate: [clientePermisoGuard('CU13')],
    data: { header: 'plataforma', encabezadoSolido: true },
  },
  { path: 'checkout', component: Checkout, canActivate: [authGuard, clientePermisoGuard('CU13')] },
  { path: 'producto/:id', component: ProductoDetalle },
  { path: 'login', component: Login, data: { hideChrome: true } },
  { path: 'registro', component: Registro, data: { hideChrome: true } },
  { path: 'recuperar', component: RecuperarPassword, data: { hideChrome: true } },
  { path: 'perfil', component: Perfil, canActivate: [authGuard] },
  {
    path: 'mis-compras/:id',
    component: Comprobante,
    canActivate: [authGuard],
    data: { hideChrome: true },
  },
  {
    path: 'admin/factura/:id',
    component: AdminFactura,
    canActivate: [adminGuard, permisoGuard('CU11')],
    data: { hideChrome: true },
  },
  {
    path: 'admin',
    component: AdminLayout,
    canActivate: [adminGuard],
    data: { hideChrome: true },
    children: [
      { path: '', component: AdminHome },
      { path: 'usuarios', component: AdminUsuarios, canActivate: [permisoGuard('CU02')] },
      { path: 'clientes', component: AdminClientes, canActivate: [permisoGuard('CU03')] },
      { path: 'sucursales', component: AdminSucursales, canActivate: [permisoGuard('CU04')] },
      { path: 'productos', component: AdminProductos, canActivate: [permisoGuard('CU05')] },
      { path: 'proveedores', component: AdminProveedores, canActivate: [permisoGuard('CU06')] },
      { path: 'temporadas', component: AdminTemporadas, canActivate: [permisoGuard('CU07')] },
      { path: 'catalogo', component: AdminCatalogo, canActivate: [permisoGuard('CU08')] },
      { path: 'inventario', component: AdminInventario, canActivate: [permisoGuard('CU12')] },
      { path: 'perfil', component: AdminPerfil },
      { path: 'suscripcion', component: AdminSuscripcion, canActivate: [adminTiendaGuard] },
      { path: 'sesiones', component: AdminSesiones, canActivate: [permisoGuard('CU01')] },
      { path: 'bitacora', component: AdminBitacora, canActivate: [permisoGuard('CU17')] },
      { path: 'ar-uso', component: AdminArUso, canActivate: [permisoGuard('CU09')] },
      { path: 'reservas', component: AdminReservas, canActivate: [permisoGuard('CU10')] },
      { path: 'ventas', component: AdminVentas, canActivate: [permisoGuard('CU11')] },
      { path: 'carritos', component: AdminCarritos, canActivate: [permisoGuard('CU13')] },
      { path: 'notificaciones', component: AdminNotificaciones, canActivate: [permisoGuard('CU14')] },
      { path: 'reportes', component: AdminReportesDashboard, canActivate: [permisoGuard('CU16')] },
      { path: 'reportes/ventas', component: ReporteVentasPage, canActivate: [permisoGuard('CU16')] },
      { path: 'reportes/asistencia', component: ReporteAsistenciaPage, canActivate: [permisoGuard('CU16')] },
      { path: 'reportes/inventario', component: ReporteInventarioPage, canActivate: [permisoGuard('CU16')] },
      { path: 'reportes/reservas', component: ReporteReservasPage, canActivate: [permisoGuard('CU16')] },
      { path: 'reportes/productos', component: ReporteProductosPage, canActivate: [permisoGuard('CU16')] },
      { path: 'recomendaciones', component: AdminRecomendaciones, canActivate: [permisoGuard('CU18')] },
      { path: 'chatbot', component: AdminChatbot, canActivate: [permisoGuard('CU19')] },
      { path: 'chatbot/:clienteId', component: AdminChatbotDetalle, canActivate: [permisoGuard('CU19')] },
      { path: 'calificaciones', component: AdminCalificaciones, canActivate: [permisoGuard('CU20')] },
    ],
  },
  // Panel del SuperAdministrador: mismo esquema que el panel de una tienda,
  // con los paquetes del 1er y 2do parcial. Reusa las pantallas del 1er
  // parcial y suma las nuevas (CU09, CU10) y las que se van construyendo.
  {
    path: 'superadmin',
    component: SuperadminLayout,
    canActivate: [superadminGuard],
    data: { hideChrome: true },
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'bitacora' },
      // 2do parcial
      { path: 'sesiones', component: AdminSesiones },
      { path: 'usuarios', component: AdminUsuarios },
      { path: 'bitacora', component: AdminBitacora },
      { path: 'empresas', component: SuperadminEmpresas },
      { path: 'planes', component: SuperadminPlanes },
      { path: 'sucursales', component: AdminSucursales },
      { path: 'productos', component: AdminProductos },
      { path: 'catalogo', component: AdminCatalogo },
      { path: 'inventario', component: AdminInventario },
      { path: 'reservas', component: AdminReservas },
      { path: 'ventas', component: AdminVentas },
      { path: 'reportes', component: AdminReportesDashboard },
      { path: 'reportes/ventas', component: ReporteVentasPage },
      { path: 'reportes/asistencia', component: ReporteAsistenciaPage },
      { path: 'reportes/inventario', component: ReporteInventarioPage },
      { path: 'reportes/reservas', component: ReporteReservasPage },
      { path: 'reportes/productos', component: ReporteProductosPage },
      { path: 'recomendaciones', component: AdminRecomendaciones },
      { path: 'cu/:codigo', component: SuperadminEnConstruccion },
      // 1er parcial (se elige la empresa primero)
      { path: 'empresa/:codigo', component: SuperadminElegirEmpresa },
      { path: 'clientes', component: AdminClientes },
      { path: 'perfil', component: AdminPerfil },
      { path: 'proveedores', component: AdminProveedores },
      { path: 'temporadas', component: AdminTemporadas },
      { path: 'ar-uso', component: AdminArUso },
      { path: 'carritos', component: AdminCarritos },
      { path: 'notificaciones', component: AdminNotificaciones },
      { path: 'chatbot', component: AdminChatbot },
      { path: 'chatbot/:clienteId', component: AdminChatbotDetalle },
      { path: 'calificaciones', component: AdminCalificaciones },
    ],
  },
];
