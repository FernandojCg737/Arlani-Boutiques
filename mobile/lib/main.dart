import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme.dart';
import 'features/auth/auth_provider.dart';
import 'features/chatbot/chatbot_provider.dart';
import 'features/notificaciones/notificaciones_provider.dart';
import 'features/storefront/cart_provider.dart';
import 'router.dart';

void main() {
  runApp(const ProviderScope(child: AtelierAranierApp()));
}

class AtelierAranierApp extends ConsumerStatefulWidget {
  const AtelierAranierApp({super.key});

  @override
  ConsumerState<AtelierAranierApp> createState() => _AtelierAranierAppState();
}

class _AtelierAranierAppState extends ConsumerState<AtelierAranierApp> {
  final _messengerKey = GlobalKey<ScaffoldMessengerState>();

  /// El logo de Arlani se ve al menos este tiempo al abrir la app, aunque la
  /// sesion se revise al instante (si no, solo se alcanza a ver un parpadeo).
  static const _tiempoLogo = Duration(milliseconds: 1800);
  bool _logoVisto = false;

  @override
  void initState() {
    super.initState();
    Future.delayed(_tiempoLogo, () {
      if (mounted) setState(() => _logoVisto = true);
    });

    // El interceptor de Dio (api_client.dart) no puede llamar a authProvider
    // directamente sin crear un ciclo de providers, asi que escribe aca; este
    // listener hace el logout forzado real.
    ref.listenManual(unauthorizedEventProvider, (previous, next) {
      if (next != null) {
        ref.read(authProvider.notifier).forceLogout(next);
        ref.read(unauthorizedEventProvider.notifier).state = null;
      }
    });

    // Muestra el mensaje de sesion vencida / cerrada en otro dispositivo,
    // igual que el banner de `sessionMessage` en la web.
    ref.listenManual(authProvider, (previous, next) {
      final message = next.sessionMessage;
      if (message != null && message != previous?.sessionMessage) {
        _messengerKey.currentState?.showSnackBar(
          SnackBar(content: Text(message), backgroundColor: AppColors.danger),
        );
        ref.read(authProvider.notifier).dismissSessionMessage();
      }
    });

    // CU11/CU14: el carrito y las notificaciones viven en el backend
    // ligados al cliente -- se recargan cada vez que cambia la sesion
    // (login/logout), igual que los efectos homologos en `header.ts` de
    // la web.
    ref.listenManual(authProvider, (previous, next) {
      if (previous?.isAuthenticated == next.isAuthenticated) return;
      if (next.isAuthenticated) {
        ref.read(cartProvider.notifier).cargar();
        ref.read(notificacionesProvider.notifier).cargar();
      } else {
        ref.read(cartProvider.notifier).limpiarLocal();
        ref.read(notificacionesProvider.notifier).limpiarLocal();
        ref.read(chatbotProvider.notifier).limpiarLocal();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    // Mientras se chequea si hay sesion guardada (bootstrap), se muestra
    // el logo + un spinner en vez de saltar directo a Home -- sin esto se
    // alcanza a ver un parpadeo de contenido antes de que el router
    // termine de decidir a donde navegar.
    final revisandoSesion = ref.watch(authProvider).bootstrapping;
    if (revisandoSesion || !_logoVisto) {
      return MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        // El indicador solo aparece si la sesion tarda mas que el logo
        // (p. ej. el servidor estaba dormido).
        home: _BootstrapSplash(esperando: revisandoSesion && _logoVisto),
      );
    }

    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: 'Arlani Boutiques',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      routerConfig: router,
      scaffoldMessengerKey: _messengerKey,
    );
  }
}

class _BootstrapSplash extends StatelessWidget {
  const _BootstrapSplash({required this.esperando});

  final bool esperando;

  @override
  Widget build(BuildContext context) {
    // Arlani Boutiques: el logo completo (bolsito + letras) al centro, sobre
    // el mismo azul noche de la pantalla nativa (sin salto de color).
    final ancho = (MediaQuery.sizeOf(context).width * 0.78).clamp(220.0, 360.0);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      // Barras del sistema del mismo azul (sin franja gris abajo).
      value: SystemUiOverlayStyle.light.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: const Color(0xFF1F2A44),
        systemNavigationBarIconBrightness: Brightness.light,
      ),
      child: Scaffold(
      backgroundColor: const Color(0xFF1F2A44),
      body: Stack(
        children: [
          Center(
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: const Duration(milliseconds: 900),
              curve: const Cubic(0.16, 1, 0.3, 1),
              builder: (context, t, child) => Opacity(
                opacity: t,
                child: Transform.scale(scale: 0.92 + 0.08 * t, child: child),
              ),
              child: Image.asset('assets/arlani_logo_completo.png', width: ancho, semanticLabel: 'Arlani Boutiques'),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 72 + MediaQuery.paddingOf(context).bottom,
            child: AnimatedOpacity(
              opacity: esperando ? 1 : 0,
              duration: const Duration(milliseconds: 300),
              child: const Center(
                child: SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(color: Color(0xFFF2B8A6), strokeWidth: 2),
                ),
              ),
            ),
          ),
        ],
      ),
      ),
    );
  }
}
