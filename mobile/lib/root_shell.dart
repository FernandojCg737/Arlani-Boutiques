import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/auth/auth_provider.dart';
import 'features/storefront/cart_provider.dart';
import 'widgets/whatsapp_float_button.dart';

/// Shell con barra inferior para las paginas de compra (Catalogos, Carrito,
/// Cuenta). "Inicio" vuelve a la portada de la plataforma, que va fuera del
/// shell con su propio encabezado y menu hamburguesa.
class RootShell extends ConsumerWidget {
  const RootShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cartCount = ref.watch(cartTotalItemsProvider);
    final auth = ref.watch(authProvider);
    final esClienteConSesion = (auth.usuario?.isCliente ?? false) && auth.hasPermiso('CU19');

    return Scaffold(
      body: Stack(
        children: [
          navigationShell,
          // Equivalente al `app-whatsapp-float` de la web: abajo a la DERECHA
          // (el chatbot va a la izquierda) y sin requerir sesion.
          const Positioned(right: 16, bottom: 16, child: WhatsappFloatButton()),
        ],
      ),
      // CU19: burbuja del chatbot de la tienda, solo para clientes con sesion.
      floatingActionButton: esClienteConSesion
          ? FloatingActionButton(
              onPressed: () => context.push('/chatbot'),
              backgroundColor: const Color(0xFF203C40),
              child: const Icon(Icons.chat_bubble_outline, color: Colors.white),
            )
          : null,
      floatingActionButtonLocation: FloatingActionButtonLocation.startFloat,
      bottomNavigationBar: BottomNavigationBar(
        // El indice 0 es "Inicio" (la portada, fuera del shell).
        currentIndex: navigationShell.currentIndex + 1,
        onTap: (index) {
          if (index == 0) {
            context.go('/');
            return;
          }
          final rama = index - 1;
          navigationShell.goBranch(rama, initialLocation: rama == navigationShell.currentIndex);
        },
        items: [
          const BottomNavigationBarItem(icon: Icon(Icons.home_outlined), activeIcon: Icon(Icons.home), label: 'Inicio'),
          const BottomNavigationBarItem(
            icon: Icon(Icons.storefront_outlined),
            activeIcon: Icon(Icons.storefront),
            label: 'Catálogos',
          ),
          BottomNavigationBarItem(
            icon: Badge(
              label: Text('$cartCount'),
              isLabelVisible: cartCount > 0,
              child: const Icon(Icons.shopping_bag_outlined),
            ),
            activeIcon: const Icon(Icons.shopping_bag),
            label: 'Carrito',
          ),
          BottomNavigationBarItem(
            icon: Icon(auth.isAuthenticated ? Icons.person : Icons.person_outline),
            label: auth.isAuthenticated ? 'Cuenta' : 'Ingresar',
          ),
        ],
      ),
    );
  }
}

/// Pantalla "Cuenta": si hay sesion redirige a Perfil, si no muestra
/// login/registro — resuelto por el router mismo (ver router.dart).
class CuentaTabRedirect extends ConsumerWidget {
  const CuentaTabRedirect({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (auth.isAuthenticated) {
        context.go('/perfil');
      } else {
        context.go('/login');
      }
    });
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}
