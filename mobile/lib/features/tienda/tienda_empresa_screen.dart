import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/producto_publico.dart';
import '../../widgets/whatsapp_float_button.dart';
import '../auth/auth_provider.dart';
import '../catalogo/catalogo_universal_screen.dart';
import '../portada/estilo_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../storefront/cart_provider.dart';
import '../storefront/catalogo_provider.dart';

/// Pagina publica de una boutique (`pages/tienda-empresa` de la web, en
/// `/tienda-<subdominio>`): su encabezado y su portada con su logo y su
/// color, su catalogo (solo sus prendas, con los mismos filtros del universal)
/// y sus sucursales. Todo sale de GET /tiendas/{subdominio}: cada tienda nueva
/// tiene su pagina con su marca apenas se crea, sin cambiar la app.
class TiendaEmpresaScreen extends ConsumerStatefulWidget {
  const TiendaEmpresaScreen({super.key, required this.subdominio});

  final String subdominio;

  @override
  ConsumerState<TiendaEmpresaScreen> createState() => _TiendaEmpresaScreenState();
}

class _TiendaEmpresaScreenState extends ConsumerState<TiendaEmpresaScreen> {
  final _scroll = ScrollController();
  final _claveCatalogo = GlobalKey();
  OrdenCatalogo _orden = OrdenCatalogo.predeterminado;
  int _reintentos = 0;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _irAlCatalogo() {
    final contexto = _claveCatalogo.currentContext;
    if (contexto != null) {
      Scrollable.ensureVisible(contexto, duration: const Duration(milliseconds: 600), curve: Curves.easeInOutCubic);
    }
  }

  List<ProductoPublico> _ordenar(List<ProductoPublico> lista) {
    final copia = [...lista];
    switch (_orden) {
      case OrdenCatalogo.menorPrecio:
        copia.sort((a, b) => a.precio.compareTo(b.precio));
      case OrdenCatalogo.mayorPrecio:
        copia.sort((a, b) => b.precio.compareTo(a.precio));
      case OrdenCatalogo.recientes:
        copia.sort((a, b) => b.id.compareTo(a.id));
      case OrdenCatalogo.predeterminado:
        break;
    }
    return copia;
  }

  @override
  Widget build(BuildContext context) {
    final sub = widget.subdominio;
    final tiendaAsync = ref.watch(tiendaPublicaProvider(sub));
    // El servidor gratuito tarda en despertar: si falla, se reintenta.
    ref.listen(tiendaPublicaProvider(sub), (_, estado) {
      if (estado.hasError && !estado.isLoading && _reintentos < 6) {
        _reintentos++;
        Future.delayed(const Duration(seconds: 4), () {
          if (mounted) ref.invalidate(tiendaPublicaProvider(sub));
        });
      }
    });

    final tienda = tiendaAsync.valueOrNull;
    // Mientras llega la marca: gris neutro, de ninguna tienda (`COLOR_NEUTRO`).
    final marca = tienda == null ? const Color(0xFF2B2B2B) : colorParaTextoBlanco(tienda.resumen.colorMarca);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: ColorCatalogo(
        color: marca,
        child: Scaffold(
          backgroundColor: const Color(0xFFF7F4F2),
          body: Stack(
            children: [
              if (tiendaAsync.isLoading && tienda == null)
                const Center(child: CircularProgressIndicator())
              else if (tienda == null)
                _SinTienda(noExiste: !tiendaAsync.hasError)
              else
                _contenido(tienda, marca),
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: EncabezadoTienda(
                  tienda: tienda,
                  marca: marca,
                  onCatalogo: _irAlCatalogo,
                  onCategoria: (c) {
                    ref.read(filtrosCatalogoProvider(sub).notifier).setCategoria(c);
                    _irAlCatalogo();
                  },
                  onBuscar: (texto) {
                    ref.read(filtrosCatalogoProvider(sub).notifier).setBusqueda(texto.trim());
                    _irAlCatalogo();
                  },
                ),
              ),
              Positioned(
                right: 16,
                bottom: 16 + MediaQuery.paddingOf(context).bottom,
                child: const WhatsappFloatButton(),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _contenido(TiendaPublica tienda, Color marca) {
    final sub = widget.subdominio;
    final productosAsync = ref.watch(productosPublicosProvider);
    final visibles = _ordenar(ref.watch(productosDeCatalogoProvider(sub)));
    final busqueda = ref.watch(filtrosCatalogoProvider(sub).select((f) => f.busqueda.trim()));
    final ancho = MediaQuery.sizeOf(context).width;
    final anchoTarjeta = (ancho - 2 * 16 - 1) / 2;
    final activa = tienda.estado == 'activa';

    return RefreshIndicator(
      edgeOffset: MediaQuery.paddingOf(context).top + EncabezadoTienda.alto,
      onRefresh: () async {
        ref.invalidate(tiendaPublicaProvider(sub));
        ref.invalidate(productosPublicosProvider);
      },
      child: CustomScrollView(
        controller: _scroll,
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(child: _PortadaTienda(tienda: tienda.resumen, marca: marca)),
          if (!activa)
            const SliverToBoxAdapter(
              child: _Aviso(
                titulo: 'Esta tienda no está disponible por ahora',
                texto: 'Vuelve a intentarlo más tarde o mira otras boutiques de Arlani.',
                conBoton: true,
              ),
            )
          else if (!tienda.tieneCatalogo)
            const SliverToBoxAdapter(
              child: _Aviso(
                titulo: 'Estamos preparando nuestro catálogo en línea',
                texto: 'Mientras tanto, visítanos en nuestras sucursales.',
              ),
            )
          else ...[
            SliverPadding(
              key: _claveCatalogo,
              padding: const EdgeInsets.fromLTRB(16, 48, 16, 32),
              sliver: SliverToBoxAdapter(child: FiltrosCatalogo(tienda: sub)),
            ),
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverToBoxAdapter(
                child: BarraResultados(
                  cantidad: visibles.length,
                  orden: _orden,
                  onOrden: (o) => setState(() => _orden = o),
                  busqueda: busqueda,
                  onQuitarBusqueda: () => ref.read(filtrosCatalogoProvider(sub).notifier).setBusqueda(''),
                ),
              ),
            ),
            if (productosAsync.isLoading && !productosAsync.hasValue)
              const SliverToBoxAdapter(
                child: Padding(padding: EdgeInsets.all(48), child: Center(child: CircularProgressIndicator())),
              )
            else if (visibles.isEmpty)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 48),
                  child: Text(
                    busqueda.isNotEmpty ? 'No encontramos productos para "$busqueda".' : 'No hay productos con estos filtros.',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.inter(color: const Color(0xFF888888), fontSize: 14),
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverGrid(
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    mainAxisSpacing: 1,
                    crossAxisSpacing: 1,
                    mainAxisExtent: anchoTarjeta * 4 / 3 + 106,
                  ),
                  delegate: SliverChildBuilderDelegate(
                    (context, i) => TarjetaProducto(producto: visibles[i], mostrarTienda: false),
                    childCount: visibles.length,
                  ),
                ),
              ),
          ],
          if (activa && tienda.sucursales.isNotEmpty)
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 48, 16, 96),
              sliver: SliverToBoxAdapter(child: _Sucursales(sucursales: tienda.sucursales, marca: marca)),
            )
          else
            const SliverToBoxAdapter(child: SizedBox(height: 96)),
        ],
      ),
    );
  }
}

// ========================================================= encabezado

/// Encabezado de una boutique (`app-header` con la tienda activa): su logo
/// sobre su color, el carrito y el menu con su catalogo, sus categorias y el
/// regreso a Arlani.
class EncabezadoTienda extends ConsumerStatefulWidget {
  const EncabezadoTienda({
    super.key,
    required this.tienda,
    required this.marca,
    required this.onCatalogo,
    required this.onCategoria,
    required this.onBuscar,
  });

  final TiendaPublica? tienda;
  final Color marca;
  final VoidCallback onCatalogo;
  final ValueChanged<String> onCategoria;
  final ValueChanged<String> onBuscar;

  static const alto = 64.0;

  @override
  ConsumerState<EncabezadoTienda> createState() => _EncabezadoTiendaState();
}

class _EncabezadoTiendaState extends ConsumerState<EncabezadoTienda> {
  bool _menu = false;
  final _busqueda = TextEditingController();

  @override
  void dispose() {
    _busqueda.dispose();
    super.dispose();
  }

  void _cerrarY(VoidCallback accion) {
    setState(() => _menu = false);
    accion();
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final enCarrito = ref.watch(cartTotalItemsProvider);
    final tienda = widget.tienda?.resumen;
    final arriba = MediaQuery.paddingOf(context).top;

    // Categorias de la tienda: las de sus prendas (como Poleras/Pantalones en la web).
    final productos = ref.watch(productosPublicosProvider).valueOrNull ?? const <ProductoPublico>[];
    final categorias = productos
        .where((p) => p.tienda == tienda?.subdominio && p.categoriaNombre.isNotEmpty)
        .map((p) => p.categoriaNombre)
        .toSet()
        .take(4)
        .toList();

    final estiloMenu = GoogleFonts.inter(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: 0.9);
    Widget enlace(String texto, VoidCallback onTap) => InkWell(
          onTap: () => _cerrarY(onTap),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 15),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.12)))),
            child: Text(texto.toUpperCase(), style: estiloMenu),
          ),
        );

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      color: widget.marca,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(height: arriba),
          SizedBox(
            height: EncabezadoTienda.alto,
            child: Row(
              children: [
                IconButton(
                  tooltip: 'Volver',
                  icon: const Icon(Icons.arrow_back, color: Colors.white),
                  onPressed: () => context.canPop() ? context.pop() : context.go('/catalogo'),
                ),
                Expanded(
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: tienda == null
                        ? const SizedBox.shrink()
                        : tienda.logoUrl != null && tienda.logoUrl!.isNotEmpty
                            ? SizedBox(
                                height: 40,
                                width: 130,
                                child: ImagenTienda(tienda.logoUrl!, contorno: tienda.logoUrl!.startsWith('http')),
                              )
                            : Text(tienda.nombre.toUpperCase(),
                                style: GoogleFonts.inter(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 16)),
                  ),
                ),
                if (auth.mostrarAccionCliente('CU13') && !auth.isStaff)
                  IconButton(
                    tooltip: 'Carrito',
                    onPressed: () => context.push('/carrito'),
                    icon: Badge(
                      isLabelVisible: enCarrito > 0,
                      label: Text('$enCarrito'),
                      child: const Icon(Icons.shopping_cart_outlined, color: Colors.white, size: 26),
                    ),
                  ),
                IconButton(
                  tooltip: _menu ? 'Cerrar menú' : 'Abrir menú',
                  icon: Icon(_menu ? Icons.close : Icons.menu, color: Colors.white, size: 28),
                  onPressed: () => setState(() => _menu = !_menu),
                ),
                const SizedBox(width: 6),
              ],
            ),
          ),
          if (_menu)
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height - arriba - EncabezadoTienda.alto),
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
                child: Column(
                  children: [
                    Container(
                      margin: const EdgeInsets.only(bottom: 4),
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(10)),
                      child: TextField(
                        controller: _busqueda,
                        textInputAction: TextInputAction.search,
                        onSubmitted: (t) => _cerrarY(() => widget.onBuscar(t)),
                        style: GoogleFonts.inter(color: Colors.white, fontSize: 16),
                        cursorColor: Colors.white,
                        decoration: InputDecoration(
                          icon: const Icon(Icons.search, color: Colors.white),
                          hintText: 'Buscar en ${tienda?.nombre ?? 'la tienda'}...',
                          hintStyle: GoogleFonts.inter(color: Colors.white.withValues(alpha: 0.65)),
                          border: InputBorder.none,
                          enabledBorder: InputBorder.none,
                          focusedBorder: InputBorder.none,
                        ),
                      ),
                    ),
                    enlace('Tienda', widget.onCatalogo),
                    for (final c in categorias) enlace(c, () => widget.onCategoria(c)),
                    enlace('Todas las boutiques', () => context.go('/catalogo')),
                    enlace('Arlani Boutiques', () => context.go('/')),
                    if (auth.usuario != null) ...[
                      enlace('Mi perfil', () => context.push('/perfil')),
                      enlace('Cerrar sesión', () => ref.read(authProvider.notifier).logout()),
                    ] else ...[
                      enlace('Iniciar sesión', () => context.push('/login')),
                      enlace('Crear una cuenta', () => context.push('/registro')),
                    ],
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

// ============================================================ portada

class _PortadaTienda extends StatelessWidget {
  const _PortadaTienda({required this.tienda, required this.marca});

  final TiendaResumen tienda;
  final Color marca;

  @override
  Widget build(BuildContext context) {
    final logo = tienda.logoUrl;
    final tam = (MediaQuery.sizeOf(context).width * 0.06).clamp(32.0, 56.0);
    return Container(
      width: double.infinity,
      color: marca,
      padding: EdgeInsets.fromLTRB(16, MediaQuery.paddingOf(context).top + EncabezadoTienda.alto + 40, 16, 56),
      child: Column(
        children: [
          if (logo != null && logo.isNotEmpty)
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 240, maxHeight: 110),
              child: ImagenTienda(logo, contorno: logo.startsWith('http')),
            )
          else
            Container(
              width: 72,
              height: 72,
              alignment: Alignment.center,
              decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Colors.white.withValues(alpha: 0.6), width: 2)),
              child: Text(tienda.nombre.isEmpty ? '?' : tienda.nombre[0].toUpperCase(),
                  style: GoogleFonts.inter(color: Colors.white, fontSize: 32, fontWeight: FontWeight.w800)),
            ),
          const SizedBox(height: 12),
          Text(tienda.nombre,
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(color: Colors.white, fontSize: tam, fontWeight: FontWeight.w800, height: 1)),
          if (tienda.ciudad != null && tienda.ciudad!.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(tienda.ciudad!, style: GoogleFonts.inter(color: Colors.white.withValues(alpha: 0.85), fontSize: 14)),
          ],
        ],
      ),
    );
  }
}

class _Sucursales extends StatelessWidget {
  const _Sucursales({required this.sucursales, required this.marca});

  final List<SucursalTienda> sucursales;
  final Color marca;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Sucursales', style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w800, color: Plataforma.azulNoche)),
        const SizedBox(height: 16),
        for (final s in sucursales)
          Container(
            margin: const EdgeInsets.only(bottom: 16),
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border(
                top: BorderSide(color: marca, width: 3),
                left: const BorderSide(color: Color(0xFFE2DDD8)),
                right: const BorderSide(color: Color(0xFFE2DDD8)),
                bottom: const BorderSide(color: Color(0xFFE2DDD8)),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(s.nombre, style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w700, color: Plataforma.azulNoche)),
                const SizedBox(height: 4),
                Text('${s.direccion}, ${s.ciudad}', style: GoogleFonts.inter(fontSize: 14, color: const Color(0xFF555555))),
                if (s.horario != null) ...[
                  const SizedBox(height: 4),
                  Text(s.horario!, style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF888888))),
                ],
                const SizedBox(height: 8),
                Wrap(
                  spacing: 16,
                  children: [
                    GestureDetector(
                      onTap: () => launchUrl(
                        Uri.parse('https://www.google.com/maps/search/?api=1&query=${Uri.encodeComponent('${s.direccion}, ${s.ciudad}')}'),
                        mode: LaunchMode.externalApplication,
                      ),
                      child: Text('Cómo llegar',
                          style: GoogleFonts.inter(
                              fontSize: 12, fontWeight: FontWeight.w700, color: Plataforma.azulNoche, decoration: TextDecoration.underline)),
                    ),
                    if (s.telefono != null && s.telefono!.isNotEmpty)
                      GestureDetector(
                        onTap: () => launchUrl(Uri.parse('tel:${s.telefono}')),
                        child: Text(s.telefono!,
                            style: GoogleFonts.inter(
                                fontSize: 12, fontWeight: FontWeight.w700, color: Plataforma.azulNoche, decoration: TextDecoration.underline)),
                      ),
                  ],
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _Aviso extends StatelessWidget {
  const _Aviso({required this.titulo, required this.texto, this.conBoton = false});

  final String titulo;
  final String texto;
  final bool conBoton;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 48, 24, 24),
      child: Column(
        children: [
          Text(titulo,
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w800, color: Plataforma.azulNoche)),
          const SizedBox(height: 8),
          Text(texto, textAlign: TextAlign.center, style: GoogleFonts.inter(fontSize: 15, color: const Color(0xFF666666))),
          if (conBoton) ...[
            const SizedBox(height: 20),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Plataforma.azulNoche, shape: const RoundedRectangleBorder()),
              onPressed: () => context.go('/'),
              child: const Text('VER BOUTIQUES'),
            ),
          ],
        ],
      ),
    );
  }
}

class _SinTienda extends StatelessWidget {
  const _SinTienda({required this.noExiste});

  final bool noExiste;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: _Aviso(
        titulo: noExiste ? 'No encontramos esta tienda' : 'No pudimos cargar la tienda',
        texto: noExiste ? 'Revisa el enlace o mira todas las boutiques de Arlani.' : 'Revisa tu conexión e inténtalo de nuevo.',
        conBoton: true,
      ),
    );
  }
}
