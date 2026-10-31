import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/admin/admin_menu.dart';
import 'features/admin/admin_shell.dart';
import 'features/admin/bitacora/bitacora_screen.dart';
import 'features/admin/calificaciones/calificaciones_admin_screen.dart';
import 'features/admin/carritos/carritos_screen.dart';
import 'features/admin/catalogo/catalogo_screen.dart';
import 'features/admin/chatbot/chatbot_admin_screen.dart';
import 'features/admin/clientes/clientes_screen.dart';
import 'features/admin/inventario/inventario_screen.dart';
import 'features/admin/notificaciones/notificaciones_admin_screen.dart';
import 'features/admin/productos/productos_screen.dart';
import 'features/admin/proveedores/proveedores_screen.dart';
import 'features/admin/recomendaciones/recomendaciones_admin_screen.dart';
import 'features/admin/reservas/reservas_screen.dart';
import 'features/admin/sesiones/sesiones_screen.dart';
import 'features/admin/sucursales/sucursales_screen.dart';
import 'features/admin/temporadas/temporadas_screen.dart';
import 'features/admin/usuarios/usuarios_screen.dart';
import 'features/admin/ventas/ventas_screen.dart';
import 'features/auth/auth_provider.dart';
import 'features/auth/login_screen.dart';
import 'features/auth/perfil_screen.dart';
import 'features/auth/recuperar_password_screen.dart';
import 'features/auth/registro_screen.dart';
import 'features/catalogo/catalogo_universal_screen.dart';
import 'features/chatbot/chatbot_screen.dart';
import 'features/portada/portada_screen.dart';
import 'features/tienda/tienda_empresa_screen.dart';
import 'features/storefront/carrito_screen.dart';
import 'features/storefront/checkout_screen.dart';
import 'features/storefront/cotizaciones_screen.dart';
import 'features/storefront/producto_detalle_screen.dart';

/// Mapa ruta admin -> codigo CU requerido, derivado de `admin_menu.dart`
/// (misma fuente que el sidebar) — equivalente a `permisoGuard('CUxx')` en
/// cada ruta hija de `/admin` en la web.
final Map<String, String> _rutaAdminPorCodigo = {
  for (final paquete in adminMenu)
    for (final cu in paquete.useCases)
      if (cu.route != null && cu.route!.startsWith('/admin/')) cu.route!: cu.code,
};

// Rutas del lado del cliente que dependen de un CU habilitado para el rol
// Cliente (CU02, pestana Cliente) -- espejo de las rutas equivalentes en
// app.routes.ts de la web (clientePermisoGuard).
const Map<String, String> _rutaClientePorCodigo = {
  '/carrito': 'CU13',
  '/checkout': 'CU11',
  '/chatbot': 'CU19',
};

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    refreshListenable: _AuthListenable(ref),
    redirect: (context, state) {
      final auth = ref.read(authProvider);
      if (auth.bootstrapping) return null;

      final loc = state.matchedLocation;
      final isAuthRoute = loc == '/login' || loc == '/registro' || loc == '/recuperar';
      final requiresAuth = loc == '/perfil' || loc == '/checkout' || loc == '/chatbot';
      final isAdminArea = loc == '/admin' || loc.startsWith('/admin/');

      if (requiresAuth && !auth.isAuthenticated) return '/login';
      if (isAdminArea && !auth.isStaff) return '/login';
      if (isAuthRoute && auth.isAuthenticated) return auth.isStaff ? '/admin' : '/';

      final codigoRequerido = _rutaAdminPorCodigo[loc];
      if (codigoRequerido != null && !auth.isAdministrador && !auth.hasPermiso(codigoRequerido)) {
        return '/admin';
      }

      // Igual que clientePermisoGuard en la web: si HAY sesion de cliente y
      // el rol Cliente no tiene el CU habilitado (CU02), manda al inicio.
      final codigoCliente = _rutaClientePorCodigo[loc];
      if (codigoCliente != null && auth.usuario != null && !auth.hasPermiso(codigoCliente)) {
        return '/';
      }
      return null;
    },
    routes: [
      // Portada de la plataforma (encabezado propio con menu hamburguesa).
      GoRoute(
        path: '/',
        builder: (context, state) => PortadaScreen(seccionInicial: state.uri.queryParameters['seccion']),
      ),
      // Catalogo universal: todas las boutiques, con el encabezado de la plataforma.
      GoRoute(path: '/catalogo', builder: (context, state) => const CatalogoUniversalScreen()),
      GoRoute(path: '/tienda', redirect: (context, state) => '/catalogo'),
      // Pagina propia de cada boutique: su marca, su catalogo y sus sucursales.
      GoRoute(
        path: '/tienda/:subdominio',
        builder: (context, state) => TiendaEmpresaScreen(subdominio: state.pathParameters['subdominio']!),
      ),
      GoRoute(path: '/asistente', builder: (context, state) => const ChatbotScreen(universal: true)),
      // Carrito de la plataforma (encabezado de Arlani, sin barra inferior).
      GoRoute(path: '/carrito', builder: (context, state) => const CarritoScreen()),
      GoRoute(
        path: '/cuenta',
        redirect: (context, state) => ProviderScope.containerOf(context).read(authProvider).isAuthenticated ? '/perfil' : '/login',
      ),
      GoRoute(path: '/cotizaciones', builder: (context, state) => const CotizacionesScreen()),
      GoRoute(path: '/checkout', builder: (context, state) => const CheckoutScreen()),
      GoRoute(path: '/chatbot', builder: (context, state) => const ChatbotScreen()),
      GoRoute(
        path: '/producto/:id',
        builder: (context, state) => ProductoDetalleScreen(productoId: int.parse(state.pathParameters['id']!)),
      ),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(path: '/registro', builder: (context, state) => const RegistroScreen()),
      GoRoute(path: '/recuperar', builder: (context, state) => const RecuperarPasswordScreen()),
      GoRoute(
        path: '/perfil',
        // ?tab=notificaciones (desde el menu), como `/perfil?tab=` en la web.
        builder: (context, state) => PerfilScreen(tabInicial: state.uri.queryParameters['tab']),
      ),
      GoRoute(path: '/admin', builder: (context, state) => const AdminShell()),
      GoRoute(path: '/admin/sesiones', builder: (context, state) => const SesionesScreen()),
      GoRoute(path: '/admin/usuarios', builder: (context, state) => const UsuariosScreen()),
      GoRoute(path: '/admin/bitacora', builder: (context, state) => const BitacoraScreen()),
      GoRoute(path: '/admin/clientes', builder: (context, state) => const ClientesScreen()),
      GoRoute(path: '/admin/sucursales', builder: (context, state) => const SucursalesScreen()),
      GoRoute(path: '/admin/productos', builder: (context, state) => const ProductosScreen()),
      GoRoute(path: '/admin/proveedores', builder: (context, state) => const ProveedoresScreen()),
      GoRoute(path: '/admin/temporadas', builder: (context, state) => const TemporadasScreen()),
      GoRoute(path: '/admin/catalogo', builder: (context, state) => const CatalogoScreen()),
      GoRoute(path: '/admin/inventario', builder: (context, state) => const InventarioScreen()),
      GoRoute(path: '/admin/reservas', builder: (context, state) => const ReservasScreen()),
      GoRoute(path: '/admin/ventas', builder: (context, state) => const VentasScreen()),
      GoRoute(path: '/admin/carritos', builder: (context, state) => const CarritosScreen()),
      GoRoute(path: '/admin/notificaciones', builder: (context, state) => const NotificacionesAdminScreen()),
      GoRoute(path: '/admin/recomendaciones', builder: (context, state) => const RecomendacionesAdminScreen()),
      GoRoute(path: '/admin/chatbot', builder: (context, state) => const ChatbotAdminScreen()),
      GoRoute(path: '/admin/calificaciones', builder: (context, state) => const CalificacionesAdminScreen()),
    ],
  );
});

/// Puentea el estado de Riverpod (AuthState) con go_router: cuando cambia
/// la sesion, go_router reevalua `redirect` automaticamente.
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(this.ref) {
    ref.listen(authProvider, (previous, next) {
      if (previous?.isAuthenticated != next.isAuthenticated || previous?.bootstrapping != next.bootstrapping) {
        notifyListeners();
      }
    });
  }

  final Ref ref;
}
