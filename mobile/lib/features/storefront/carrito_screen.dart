import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/theme.dart';
import '../../models/carrito.dart';
import '../../widgets/whatsapp_float_button.dart';
import '../auth/auth_provider.dart';
import '../portada/encabezado_plataforma.dart';
import '../portada/estilo_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../portada/secciones_cierre.dart';
import 'cart_provider.dart';
import 'catalogo_provider.dart';
import 'reserva_form_screen.dart';
import 'reservar_carrito_screen.dart';

const _borde = Color(0xFFE6E1DC);

/// CU11: el carrito de la plataforma, igual que `pages/carrito` de la web:
/// encabezado de Arlani, "Seguir comprando" (vuelve atras), las prendas
/// agrupadas por la boutique que las vende, el resumen con "Finalizar compra"
/// y "Reservar y pagar en sucursal", y el pie de la plataforma.
class CarritoScreen extends ConsumerStatefulWidget {
  const CarritoScreen({super.key});

  @override
  ConsumerState<CarritoScreen> createState() => _CarritoScreenState();
}

class _CarritoScreenState extends ConsumerState<CarritoScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (ref.read(authProvider).usuario?.isCliente ?? false) ref.read(cartProvider.notifier).cargar();
    });
  }

  /// "Seguir comprando": vuelve a la pagina anterior; si se entro directo, al catalogo.
  void _volver() => context.canPop() ? context.pop() : context.go('/catalogo');

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final state = ref.watch(cartProvider);
    final items = state.items;
    final arriba = MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto;

    final Widget cuerpo;
    if (!auth.isAuthenticated) {
      cuerpo = _Vacio(
        titulo: 'Inicia sesión para ver tu carrito',
        texto: 'Tu carrito se guarda en tu cuenta: inicia sesión o crea una cuenta para agregar prendas y comprar.',
        botones: [
          _Boton(texto: 'Iniciar sesión', lleno: true, onTap: () => context.push('/login')),
          _Boton(texto: 'Crear una cuenta', onTap: () => context.push('/registro')),
        ],
      );
    } else if (!auth.hasPermiso('CU13')) {
      cuerpo = const _Vacio(
        titulo: 'El carrito no está disponible',
        texto: 'Tu cuenta no tiene habilitado el carrito de compras por el momento.',
        botones: [],
      );
    } else if (state.loading && items.isEmpty) {
      cuerpo = const Padding(padding: EdgeInsets.all(48), child: Center(child: CircularProgressIndicator()));
    } else if (items.isEmpty) {
      cuerpo = _Vacio(
        titulo: 'Tu carrito está vacío',
        texto: 'Explora las boutiques de Arlani y agrega las prendas que te gusten.',
        botones: [
          _Boton(texto: 'Explorar boutiques', lleno: true, onTap: () => context.go('/?seccion=boutiques')),
          _Boton(texto: 'Ver promociones', onTap: () => context.go('/?seccion=promociones')),
        ],
      );
    } else {
      cuerpo = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final grupo in _agrupar(items)) ...[_GrupoTienda(items: grupo), const SizedBox(height: 20)],
          const SizedBox(height: 4),
          _Resumen(items: items, total: state.total, totalItems: state.totalItems),
        ],
      );
    }

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: Plataforma.marfil,
        body: Stack(
          children: [
            RefreshIndicator(
              edgeOffset: arriba,
              onRefresh: () => ref.read(cartProvider.notifier).cargar(),
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      padding: EdgeInsets.fromLTRB(20, arriba + 40, 20, 88),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Align(
                            alignment: Alignment.centerLeft,
                            child: InkWell(
                              onTap: _volver,
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.chevron_left, size: 18, color: Plataforma.gris),
                                  Text('Seguir comprando',
                                      style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600, color: Plataforma.gris)),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: 22),
                          Text('TU CARRITO', style: antetituloPlataforma(Plataforma.coralOscuro).copyWith(fontSize: 12.5, letterSpacing: 1.25)),
                          const SizedBox(height: 10),
                          Text('CARRITO DE COMPRAS', style: tituloPlataforma(size: 35.2, color: Plataforma.noche)),
                          const SizedBox(height: 12),
                          Text('Revisa las prendas que elegiste antes de finalizar la compra o reservarlas.',
                              style: GoogleFonts.inter(fontSize: 16, color: Plataforma.gris, height: 1.4)),
                          const SizedBox(height: 36),
                          cuerpo,
                        ],
                      ),
                    ),
                    PiePlataforma(onIrA: (s) => context.go(s == SeccionPortada.inicio ? '/' : '/?seccion=${s.name}')),
                  ],
                ),
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: EncabezadoPlataforma(
                solido: true,
                pleno: true,
                onIrA: (s) => context.go(s == SeccionPortada.inicio ? '/' : '/?seccion=${s.name}'),
                onBuscar: (texto) {
                  ref.read(tiendaFiltrosProvider.notifier).setBusqueda(texto.trim());
                  context.go('/catalogo');
                },
              ),
            ),
            Positioned(right: 16, bottom: 16 + MediaQuery.paddingOf(context).bottom, child: const WhatsappFloatButton()),
          ],
        ),
      ),
    );
  }
}

// ================================================================= vacio

/// `.vacio`: la bolsa de Arlani, un titulo, un texto y los botones.
class _Vacio extends StatelessWidget {
  const _Vacio({required this.titulo, required this.texto, required this.botones});

  final String titulo;
  final String texto;
  final List<Widget> botones;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 48),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20)),
      child: Column(
        children: [
          Container(
            decoration: const BoxDecoration(
              boxShadow: [BoxShadow(color: Color(0x2E121A2C), blurRadius: 24, offset: Offset(0, 16), spreadRadius: -12)],
            ),
            child: Image.asset('assets/portada/arlani-icono-512.png', width: 96, height: 96),
          ),
          const SizedBox(height: 18),
          Text(titulo,
              textAlign: TextAlign.center,
              style: GoogleFonts.outfit(fontSize: 26, fontWeight: FontWeight.w600, color: Plataforma.noche, height: 1.2)),
          const SizedBox(height: 10),
          Text(texto, textAlign: TextAlign.center, style: GoogleFonts.inter(fontSize: 15, color: Plataforma.gris, height: 1.6)),
          if (botones.isNotEmpty) ...[
            const SizedBox(height: 28),
            Wrap(alignment: WrapAlignment.center, spacing: 12, runSpacing: 12, children: botones),
          ],
        ],
      ),
    );
  }
}

/// `.boton`: pildora con borde o llena de azul noche.
class _Boton extends StatelessWidget {
  const _Boton({required this.texto, required this.onTap, this.lleno = false, this.ancho = false});

  final String texto;
  final VoidCallback? onTap;
  final bool lleno;
  final bool ancho;

  @override
  Widget build(BuildContext context) {
    final boton = Material(
      color: lleno ? Plataforma.noche : Colors.transparent,
      shape: StadiumBorder(side: BorderSide(color: lleno ? Plataforma.noche : const Color(0x38121A2C), width: 1.5)),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          child: Text(
            texto,
            textAlign: TextAlign.center,
            style: GoogleFonts.inter(fontSize: 15.2, fontWeight: FontWeight.w700, color: lleno ? Colors.white : Plataforma.noche),
          ),
        ),
      ),
    );
    return ancho ? SizedBox(width: double.infinity, child: boton) : boton;
  }
}

// ================================================================ grupos

/// Prendas agrupadas por la boutique que las vende, en el orden en que se
/// agregaron (`grupos` en carrito.ts de la web).
List<List<DetalleCarrito>> _agrupar(List<DetalleCarrito> items) {
  final grupos = <String, List<DetalleCarrito>>{};
  for (final item in items) {
    grupos.putIfAbsent(item.tienda ?? '', () => []).add(item);
  }
  return grupos.values.toList();
}

/// `.grupo`: "Vendido por" con el logo de la tienda, "Ver catalogo", sus
/// prendas y el subtotal en esa tienda.
class _GrupoTienda extends StatelessWidget {
  const _GrupoTienda({required this.items});

  final List<DetalleCarrito> items;

  @override
  Widget build(BuildContext context) {
    final primero = items.first;
    final nombre = primero.tiendaNombre ?? 'Atelier Aranier';
    final logo = primero.tiendaLogo ?? '/img/logo.png';
    final subtotal = items.fold<double>(0, (suma, i) => suma + i.subtotal);
    final fondoLogo = colorMarca(primero.tiendaColor);

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [BoxShadow(color: Color(0x0A121A2C), blurRadius: 2, offset: Offset(0, 1))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _borde))),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  padding: const EdgeInsets.all(5),
                  decoration: BoxDecoration(
                    // El logo va sobre el color de su tienda para que se vea
                    // aunque sea blanco (el de Atelier) u oscuro.
                    color: fondoLogo,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: _borde),
                  ),
                  child: ImagenTienda(logo),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Vendido por', style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w600, color: Plataforma.gris)),
                      Text(nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: Plataforma.noche)),
                    ],
                  ),
                ),
                GestureDetector(
                  onTap: () => context.push('/tienda/${primero.tienda ?? tiendaOriginal}'),
                  child: Text('Ver catálogo',
                      style: GoogleFonts.inter(fontSize: 13.6, fontWeight: FontWeight.w700, color: Plataforma.coralOscuro)),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              children: [
                for (var i = 0; i < items.length; i++) ...[
                  if (i > 0) const Divider(height: 1, color: _borde),
                  _ItemCarrito(item: items[i]),
                ],
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
            decoration: const BoxDecoration(border: Border(top: BorderSide(color: _borde))),
            child: Row(
              children: [
                Expanded(
                  child: Text('Subtotal en $nombre', style: GoogleFonts.inter(fontSize: 14.4, color: Plataforma.gris)),
                ),
                Text('${subtotal.toStringAsFixed(2)} Bs',
                    style: GoogleFonts.inter(fontSize: 14.4, fontWeight: FontWeight.w700, color: Plataforma.noche)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// `.item`: foto 4/5, nombre, talla y color, sucursal de retiro, precio
/// unitario, cantidad, subtotal y quitar.
class _ItemCarrito extends ConsumerWidget {
  const _ItemCarrito({required this.item});

  final DetalleCarrito item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final carrito = ref.read(cartProvider.notifier);
    final gris = GoogleFonts.inter(fontSize: 13.4, color: Plataforma.gris);

    return Stack(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 18),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  width: 84,
                  height: 105,
                  color: Plataforma.marfil,
                  child: item.productoImagenUrl != null
                      ? CachedNetworkImage(imageUrl: item.productoImagenUrl!, fit: BoxFit.cover, alignment: Alignment.topCenter)
                      : null,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(right: 36),
                      child: Text(item.productoNombre,
                          style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: Plataforma.noche)),
                    ),
                    const SizedBox(height: 3),
                    Text('Talla ${item.tallaCodigo} · ${item.colorNombre}', style: gris),
                    const SizedBox(height: 3),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 1),
                          child: Icon(Icons.location_on_outlined, size: 14, color: Plataforma.gris),
                        ),
                        const SizedBox(width: 4),
                        Expanded(child: Text('Retiro en ${item.sucursalNombre}', style: gris.copyWith(fontSize: 13))),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text('${item.precioUnitario.toStringAsFixed(2)} Bs c/u', style: gris),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        _Cantidad(
                          cantidad: item.cantidad,
                          onMenos: () => carrito.actualizarCantidad(item.id, item.cantidad - 1),
                          onMas: () => carrito.actualizarCantidad(item.id, item.cantidad + 1),
                        ),
                        const Spacer(),
                        Text('${item.subtotal.toStringAsFixed(2)} Bs',
                            style: bricolage(size: 18.4, weight: FontWeight.w500, color: Plataforma.noche)),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Positioned(
          top: 12,
          right: -8,
          child: IconButton(
            tooltip: 'Quitar ${item.productoNombre} del carrito',
            icon: const Icon(Icons.delete_outline, size: 20, color: Plataforma.gris),
            onPressed: () => carrito.eliminar(item.id),
          ),
        ),
      ],
    );
  }
}

class _Cantidad extends StatelessWidget {
  const _Cantidad({required this.cantidad, required this.onMenos, required this.onMas});

  final int cantidad;
  final VoidCallback onMenos;
  final VoidCallback onMas;

  @override
  Widget build(BuildContext context) {
    Widget boton(String texto, VoidCallback onTap, String descripcion) => Semantics(
          button: true,
          label: descripcion,
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(
              width: 36,
              height: 36,
              child: Center(child: Text(texto, style: GoogleFonts.inter(fontSize: 17.6, color: Plataforma.noche))),
            ),
          ),
        );

    return Container(
      decoration: BoxDecoration(border: Border.all(color: _borde, width: 1.5), borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          boton('−', onMenos, 'Restar uno'),
          SizedBox(
            width: 28,
            child: Text('$cantidad',
                textAlign: TextAlign.center, style: GoogleFonts.inter(fontWeight: FontWeight.w700, color: Plataforma.noche)),
          ),
          boton('+', onMas, 'Sumar uno'),
        ],
      ),
    );
  }
}

// =============================================================== resumen

class _Resumen extends ConsumerWidget {
  const _Resumen({required this.items, required this.total, required this.totalItems});

  final List<DetalleCarrito> items;
  final double total;
  final int totalItems;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final gris = GoogleFonts.inter(fontSize: 14.7, color: Plataforma.gris);

    Widget garantia(IconData icono, String texto) => Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: Row(
            children: [
              Icon(icono, size: 18, color: Plataforma.gris),
              const SizedBox(width: 10),
              Expanded(child: Text(texto, style: GoogleFonts.inter(fontSize: 13.4, color: Plataforma.gris))),
            ],
          ),
        );

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('RESUMEN',
              style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w700, letterSpacing: 1.25, color: Plataforma.gris)),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(child: Text('$totalItems ${totalItems == 1 ? 'prenda' : 'prendas'}', style: gris)),
              Text('${total.toStringAsFixed(2)} Bs', style: gris),
            ],
          ),
          Container(
            margin: const EdgeInsets.only(top: 16, bottom: 8),
            padding: const EdgeInsets.only(top: 14),
            decoration: const BoxDecoration(border: Border(top: BorderSide(color: _borde))),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Expanded(
                  child: Text('Total', style: GoogleFonts.inter(fontWeight: FontWeight.w700, color: Plataforma.noche)),
                ),
                Text('${total.toStringAsFixed(2)} Bs', style: bricolage(size: 32, weight: FontWeight.w500, color: Plataforma.noche)),
              ],
            ),
          ),
          const SizedBox(height: 4),
          if (auth.hasPermiso('CU11')) ...[
            _Boton(texto: 'Finalizar compra', lleno: true, ancho: true, onTap: () => context.push('/checkout')),
            const SizedBox(height: 12),
          ],
          if (auth.hasPermiso('CU10'))
            _Boton(texto: 'Reservar y pagar en sucursal', ancho: true, onTap: () => _irAReservar(context, items)),
          Container(
            margin: const EdgeInsets.only(top: 22),
            padding: const EdgeInsets.only(top: 16),
            decoration: const BoxDecoration(border: Border(top: BorderSide(color: _borde))),
            child: Column(
              children: [
                garantia(Icons.shield_outlined, 'Pagos con QR, PayPal o en efectivo'),
                garantia(Icons.location_on_outlined, 'Retiro en la sucursal que elegiste'),
              ],
            ),
          ),
        ],
      ),
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

