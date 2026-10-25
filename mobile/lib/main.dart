import 'package:flutter/material.dart';
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

  @override
  void initState() {
    super.initState();

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
    if (ref.watch(authProvider).bootstrapping) {
      return MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        home: const _BootstrapSplash(),
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
  const _BootstrapSplash();

  @override
  Widget build(BuildContext context) {
    // Arlani Boutiques: el logo completo (bolsito + letras) sobre azul noche.
    return Scaffold(
      backgroundColor: const Color(0xFF1F2A44),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Image.asset('assets/arlani_logo_completo.png', width: 300, semanticLabel: 'Arlani Boutiques'),
            ),
            const SizedBox(height: 40),
            const CircularProgressIndicator(color: Color(0xFFF2B8A6), strokeWidth: 3),
          ],
        ),
      ),
    );
  }
}
