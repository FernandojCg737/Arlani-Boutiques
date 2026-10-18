import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../../models/carrito.dart';
import '../auth/auth_provider.dart';
import '../auth/login_requerido.dart';
import 'cart_provider.dart';
import 'reserva_form_screen.dart';
import 'reservar_carrito_screen.dart';

/// CU11: replica de `pages/carrito/carrito.html` en la web, pero contra el
/// carrito real del backend (no local). Mismo header, mismo estado vacio,
/// misma lista de items + resumen con total y boton de checkout.
class CarritoScreen extends ConsumerWidget {
  const CarritoScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    // Sin sesion: la pestana se sigue viendo, pero explica que el carrito
    // se guarda en la cuenta e invita a iniciar sesion (antes decia "no esta
    // disponible por el momento", que confundia a los visitantes).
    if (!auth.isAuthenticated) return const _CarritoSinSesion();
    if (!auth.hasPermiso('CU13')) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'El carrito de compras no esta disponible por el momento.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 15, color: AppColors.grayTextDark),
          ),
        ),
      );
    }

    final state = ref.watch(cartProvider);
    final items = state.items;

    return RefreshIndicator(
      onRefresh: () => ref.read(cartProvider.notifier).cargar(),
      child: CustomScrollView(
        slivers: [
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              20,
              MediaQuery.of(context).padding.top + 20,
              20,
              0,
            ),
            sliver: SliverToBoxAdapter(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'CARRITO DE COMPRAS',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                      fontStyle: FontStyle.italic,
                      color: AppColors.brandDark,
                      letterSpacing: -0.2,
                    ),
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Revisa tus articulos seleccionados antes de finalizar la compra.',
                    style: TextStyle(
                      fontSize: 14,
                      color: AppColors.grayTextDark,
                    ),
                  ),
                ],
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
            sliver: SliverFillRemaining(
              hasScrollBody: false,
              child: Center(
                child: state.loading && items.isEmpty
                    ? const CircularProgressIndicator()
                    : items.isEmpty
                    ? const _CarritoEmpty()
                    : _CarritoContent(
                        items: items,
                        total: state.total,
                        totalItems: state.totalItems,
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CarritoSinSesion extends ConsumerWidget {
  const _CarritoSinSesion();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Container(
          width: double.infinity,
          color: const Color(0xFFF7F7F5),
          padding: const EdgeInsets.symmetric(vertical: 56, horizontal: 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const EyebrowText('Carrito', color: Color(0xFF9AA5AC)),
              const SizedBox(height: 12),
              const Text(
                'INICIA SESION PARA VER TU CARRITO',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.brandDark),
              ),
              const SizedBox(height: 12),
              const Text(
                'Tu carrito se guarda en tu cuenta: inicia sesion o crea una cuenta para agregar productos y comprar.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 14, color: AppColors.grayTextDark),
              ),
              const SizedBox(height: 28),
              ElevatedButton(
                onPressed: () => asegurarSesion(context, ref, accion: 'para ver tu carrito de compras'),
                child: const Text('INICIAR SESION'),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => context.go('/tienda'),
                child: const Text('Seguir viendo la tienda', style: TextStyle(color: AppColors.grayText)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CarritoEmpty extends StatelessWidget {
  const _CarritoEmpty();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: const Color(0xFFF7F7F5),
      padding: const EdgeInsets.symmetric(vertical: 56, horizontal: 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const EyebrowText('Carrito', color: Color(0xFF9AA5AC)),
          const SizedBox(height: 12),
          const Text(
            'TU CARRITO ESTA VACIO',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
              color: AppColors.brandDark,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Agrega productos a tu carrito para comenzar',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 14, color: AppColors.grayTextDark),
          ),
          const SizedBox(height: 28),
          ElevatedButton(
            onPressed: () => context.go('/tienda'),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('CONTINUAR COMPRANDO'),
                SizedBox(width: 10),
                Icon(Icons.arrow_forward, size: 16),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CarritoContent extends ConsumerWidget {
  const _CarritoContent({
    required this.items,
    required this.total,
    required this.totalItems,
  });

  final List<DetalleCarrito> items;
  final double total;
  final int totalItems;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DecoratedBox(
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: Color(0xFFE5E5E5))),
          ),
          child: Column(
            children: [for (final item in items) _CarritoItemRow(item: item)],
          ),
        ),
        const SizedBox(height: 24),
        Container(
          width: double.infinity,
          color: const Color(0xFFF7F7F5),
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text(
                    'TOTAL ($totalItems ARTICULOS)',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF666666),
                      letterSpacing: 0.4,
                    ),
                  ),
                  Text(
                    '${total.toStringAsFixed(2)} Bs',
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                      color: AppColors.brandDark,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (auth.hasPermiso('CU11'))
                ElevatedButton(
                  onPressed: () => context.push('/checkout'),
                  child: const Text('FINALIZAR COMPRA'),
                ),
              if (auth.hasPermiso('CU10')) ...[
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: () => _irAReservar(context, items),
                  icon: const Icon(Icons.event_outlined, size: 16),
                  label: const Text('RESERVAR'),
                  style: OutlinedButton.styleFrom(
                    shape: const RoundedRectangleBorder(),
                  ),
                ),
              ],
              const SizedBox(height: 12),
              Center(
                child: TextButton(
                  onPressed: () => context.go('/tienda'),
                  child: const Text(
                    'Continuar comprando',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.brandDark,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

const _todoElCarrito = Object();

/// Abre el flujo de reserva (CU10) desde el carrito. Si hay un solo
/// producto, va directo a reservarlo (deja elegir sucursal/talla/color
/// libremente, como desde el detalle de producto). Si hay varios, muestra
/// una hoja para elegir entre reservar TODO el carrito junto -- una sola
/// reserva con un detalle por producto, igual que "Reservar para pagar y
/// recoger en sucursal" en la web -- o reservar un unico producto.
Future<void> _irAReservar(
  BuildContext context,
  List<DetalleCarrito> items,
) async {
  if (items.length == 1) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ReservaFormScreen(
          productoId: items.first.productoId,
          productoNombre: items.first.productoNombre,
        ),
      ),
    );
    return;
  }

  final resultado = await showModalBottomSheet<Object>(
    context: context,
    builder: (context) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
            child: OutlinedButton.icon(
              onPressed: () => Navigator.of(context).pop(_todoElCarrito),
              icon: const Icon(Icons.event_available_outlined),
              label: Text('RESERVAR TODO EL CARRITO (${items.length})'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.brandWhite,
                backgroundColor: AppColors.brandDark,
                side: BorderSide.none,
                shape: const RoundedRectangleBorder(),
                minimumSize: const Size.fromHeight(48),
              ),
            ),
          ),
          const Divider(height: 1),
          const Padding(
            padding: EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'O RESERVA UN SOLO PRODUCTO',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.4,
                  color: AppColors.grayText,
                ),
              ),
            ),
          ),
          for (final item in items)
            ListTile(
              title: Text(
                '${item.productoNombre} (${item.tallaCodigo}, ${item.colorNombre})',
              ),
              onTap: () => Navigator.of(context).pop(item),
            ),
          const SizedBox(height: 12),
        ],
      ),
    ),
  );

  if (resultado == null || !context.mounted) return;

  if (identical(resultado, _todoElCarrito)) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ReservarCarritoScreen(items: items)),
    );
    return;
  }

  final elegido = resultado as DetalleCarrito;
  Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => ReservaFormScreen(
        productoId: elegido.productoId,
        productoNombre: elegido.productoNombre,
      ),
    ),
  );
}

class _CarritoItemRow extends ConsumerWidget {
  const _CarritoItemRow({required this.item});

  final DetalleCarrito item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFFE5E5E5))),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Container(
              width: 60,
              height: 76,
              color: AppColors.grayBorderLight,
              child: item.productoImagenUrl != null
                  ? CachedNetworkImage(
                      imageUrl: item.productoImagenUrl!,
                      fit: BoxFit.cover,
                    )
                  : const Icon(
                      Icons.image_not_supported_outlined,
                      color: AppColors.grayText,
                      size: 20,
                    ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${item.tallaCodigo} · ${item.colorNombre}',
                    style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF9A9A9A),
                      letterSpacing: 0.4,
                    ),
                  ),
                  Text(
                    'Retiro en ${item.sucursalNombre}',
                    style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF9A9A9A),
                      letterSpacing: 0.4,
                    ),
                  ),
                  Text(
                    item.productoNombre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: AppColors.brandDark,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${item.precioUnitario.toStringAsFixed(2)} Bs',
                    style: const TextStyle(
                      fontSize: 12,
                      color: Color(0xFF888888),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            _QtyStepper(
              quantity: item.cantidad,
              onDecrease: () => ref
                  .read(cartProvider.notifier)
                  .actualizarCantidad(item.id, item.cantidad - 1),
              onIncrease: () => ref
                  .read(cartProvider.notifier)
                  .actualizarCantidad(item.id, item.cantidad + 1),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 64,
              child: Text(
                '${item.subtotal.toStringAsFixed(2)} Bs',
                textAlign: TextAlign.right,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  color: AppColors.brandDark,
                ),
              ),
            ),
            IconButton(
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
              icon: const Icon(
                Icons.close,
                size: 16,
                color: AppColors.grayText,
              ),
              onPressed: () =>
                  ref.read(cartProvider.notifier).eliminar(item.id),
            ),
          ],
        ),
      ),
    );
  }
}

class _QtyStepper extends StatelessWidget {
  const _QtyStepper({
    required this.quantity,
    required this.onDecrease,
    required this.onIncrease,
  });

  final int quantity;
  final VoidCallback onDecrease;
  final VoidCallback onIncrease;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _QtyButton(label: '−', onTap: onDecrease),
        SizedBox(
          width: 22,
          child: Text(
            '$quantity',
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: AppColors.brandDark,
            ),
          ),
        ),
        _QtyButton(label: '+', onTap: onIncrease),
      ],
    );
  }
}

class _QtyButton extends StatelessWidget {
  const _QtyButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 26,
        height: 26,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          border: Border.all(color: AppColors.grayBorder),
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 14, color: AppColors.brandDark),
        ),
      ),
    );
  }
}
