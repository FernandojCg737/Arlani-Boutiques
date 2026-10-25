import 'dart:math' as math;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:video_player/video_player.dart';

import '../../models/producto_publico.dart';
import '../portada/encabezado_plataforma.dart';
import '../portada/estilo_plataforma.dart';
import '../portada/flotantes_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../storefront/catalogo_provider.dart';

/// Azul noche de la plataforma: el "color de marca" del catalogo universal.
const _marca = Plataforma.noche;

/// Catalogo universal (`pages/catalogo-universal` de la web): las prendas de
/// todas las boutiques de Arlani en un solo lugar. Encabezado de la
/// plataforma, portada con video, los filtros (con Boutique y Para quien) y la
/// grilla, donde cada prenda dice de que boutique es.
class CatalogoUniversalScreen extends ConsumerStatefulWidget {
  const CatalogoUniversalScreen({super.key});

  @override
  ConsumerState<CatalogoUniversalScreen> createState() => _CatalogoUniversalScreenState();
}

enum _Orden { predeterminado, menorPrecio, mayorPrecio, recientes }

const _etiquetasOrden = {
  _Orden.predeterminado: 'Predeterminado',
  _Orden.menorPrecio: 'Precio: menor a mayor',
  _Orden.mayorPrecio: 'Precio: mayor a menor',
  _Orden.recientes: 'Mas recientes',
};

class _CatalogoUniversalScreenState extends ConsumerState<CatalogoUniversalScreen> {
  final _scroll = ScrollController();
  bool _solido = false;
  bool _pasoElHero = false;
  _Orden _orden = _Orden.predeterminado;
  final _reintentos = <ProviderOrFamily, int>{};

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final y = _scroll.offset;
      final solido = y > 24;
      final pasoElHero = y >= MediaQuery.sizeOf(context).height * 0.4;
      if (solido != _solido || pasoElHero != _pasoElHero) {
        setState(() {
          _solido = solido;
          _pasoElHero = pasoElHero;
        });
      }
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  /// El servidor gratuito tarda en despertar: si la carga falla, se reintenta.
  void _reintentar(AsyncValue<Object?> estado, FutureProvider<Object?> proveedor) {
    if (!estado.hasError || estado.isLoading) return;
    final intentos = _reintentos[proveedor] ?? 0;
    if (intentos >= 6) return;
    _reintentos[proveedor] = intentos + 1;
    Future.delayed(const Duration(seconds: 4), () {
      if (mounted) ref.invalidate(proveedor);
    });
  }

  List<ProductoPublico> _ordenar(List<ProductoPublico> lista) {
    final copia = [...lista];
    switch (_orden) {
      case _Orden.menorPrecio:
        copia.sort((a, b) => a.precio.compareTo(b.precio));
      case _Orden.mayorPrecio:
        copia.sort((a, b) => b.precio.compareTo(a.precio));
      case _Orden.recientes:
        copia.sort((a, b) => b.id.compareTo(a.id));
      case _Orden.predeterminado:
        break;
    }
    return copia;
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(productosPublicosProvider, (_, e) => _reintentar(e, productosPublicosProvider));
    final productosAsync = ref.watch(productosPublicosProvider);
    final visibles = _ordenar(ref.watch(productosFiltradosProvider));
    final busqueda = ref.watch(tiendaFiltrosProvider.select((f) => f.busqueda.trim()));
    final ancho = MediaQuery.sizeOf(context).width;
    final anchoTarjeta = (ancho - 2 * Plataforma.margen - 1) / 2;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: Colors.white,
        body: Stack(
          children: [
            RefreshIndicator(
              edgeOffset: MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto,
              onRefresh: () async => ref.invalidate(productosPublicosProvider),
              child: CustomScrollView(
                controller: _scroll,
                physics: const AlwaysScrollableScrollPhysics(),
                slivers: [
                  const SliverToBoxAdapter(child: _HeroCatalogo()),
                  const SliverPadding(
                    padding: EdgeInsets.fromLTRB(Plataforma.margen, 32, Plataforma.margen, 32),
                    sliver: SliverToBoxAdapter(child: _FiltrosCatalogo()),
                  ),
                  SliverPadding(
                    padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
                    sliver: SliverToBoxAdapter(
                      child: _BarraResultados(
                        cantidad: visibles.length,
                        orden: _orden,
                        onOrden: (o) => setState(() => _orden = o),
                        busqueda: busqueda,
                        onQuitarBusqueda: () => ref.read(tiendaFiltrosProvider.notifier).setBusqueda(''),
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
                          busqueda.isNotEmpty
                              ? 'No encontramos productos para "$busqueda".'
                              : productosAsync.hasError
                                  ? 'Estamos despertando el servidor; los productos aparecen en unos segundos.'
                                  : 'No hay productos con estos filtros.',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.inter(color: const Color(0xFF888888), fontSize: 14),
                        ),
                      ),
                    )
                  else
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(Plataforma.margen, 0, Plataforma.margen, 96),
                      sliver: SliverGrid(
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          mainAxisSpacing: 1,
                          crossAxisSpacing: 1,
                          mainAxisExtent: anchoTarjeta * 4 / 3 + 128,
                        ),
                        delegate: SliverChildBuilderDelegate(
                          (context, i) => _TarjetaProducto(producto: visibles[i]),
                          childCount: visibles.length,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: EncabezadoPlataforma(
                solido: _solido,
                onIrA: (s) => context.go(s == SeccionPortada.inicio ? '/' : '/?seccion=${s.name}'),
                onBuscar: (texto) {
                  ref.read(tiendaFiltrosProvider.notifier).setBusqueda(texto.trim());
                  _scroll.animateTo(
                    MediaQuery.sizeOf(context).height * 0.45,
                    duration: const Duration(milliseconds: 500),
                    curve: Curves.easeInOutCubic,
                  );
                },
              ),
            ),
            FlotantesPlataforma(visible: _pasoElHero),
          ],
        ),
      ),
    );
  }
}

// =================================================================== hero

/// Portada de media pantalla con el video de la tienda (`size="half"`, centrada).
class _HeroCatalogo extends StatefulWidget {
  const _HeroCatalogo();

  @override
  State<_HeroCatalogo> createState() => _HeroCatalogoState();
}

class _HeroCatalogoState extends State<_HeroCatalogo> {
  late final VideoPlayerController _video;
  bool _listo = false;

  @override
  void initState() {
    super.initState();
    _video = VideoPlayerController.asset('assets/video/tienda-hero.mp4')
      ..setLooping(true)
      ..setVolume(0)
      ..initialize().then((_) {
        if (!mounted) return;
        setState(() => _listo = true);
        _video.play();
      });
  }

  @override
  void dispose() {
    _video.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pantalla = MediaQuery.sizeOf(context);
    final tamTitulo = (pantalla.width * 0.09).clamp(30.0, 64.0);

    return SizedBox(
      height: math.max(340.0, pantalla.height * 0.5),
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: [
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF203C40), Color(0xFF0F1E20)],
              ),
            ),
          ),
          if (_listo)
            ClipRect(
              child: FittedBox(
                fit: BoxFit.cover,
                child: SizedBox(width: _video.value.size.width, height: _video.value.size.height, child: VideoPlayer(_video)),
              ),
            ),
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color(0x73000000), Color(0x59000000), Color(0x8C000000)],
                stops: [0, 0.4, 1],
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(20, MediaQuery.paddingOf(context).top + 40, 20, 20),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.white.withValues(alpha: 0.5)),
                      color: Colors.black.withValues(alpha: 0.12),
                    ),
                    child: Text('ARLANI BOUTIQUES',
                        style: GoogleFonts.inter(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.9)),
                  ),
                  const SizedBox(height: 16),
                  Text('CATÁLOGO UNIVERSAL', textAlign: TextAlign.center, style: tituloPlataforma(size: tamTitulo)),
                  const SizedBox(height: 12),
                  Text(
                    'Las prendas de todas nuestras boutiques en un solo lugar. Compra en línea o reserva y retira en la sucursal de cada tienda.',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.inter(color: Colors.white.withValues(alpha: 0.9), fontSize: 14, height: 1.5),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ================================================================ filtros

/// `shop-filters` de la web: en celular va arriba de la grilla, completo.
class _FiltrosCatalogo extends ConsumerStatefulWidget {
  const _FiltrosCatalogo();

  @override
  ConsumerState<_FiltrosCatalogo> createState() => _FiltrosCatalogoState();
}

class _FiltrosCatalogoState extends ConsumerState<_FiltrosCatalogo> {
  static const _precioMin = 0.0;
  static const _precioMax = 3500.0;

  bool _categoriasAbiertas = true;
  bool _precioAbierto = true;
  RangeValues _rango = const RangeValues(_precioMin, _precioMax);

  void _aplicarPrecio(RangeValues r) {
    setState(() => _rango = r);
    ref.read(tiendaFiltrosProvider.notifier).setPrecio(
          r.start <= _precioMin ? null : r.start,
          r.end >= _precioMax ? null : r.end,
        );
  }

  @override
  Widget build(BuildContext context) {
    final filtros = ref.watch(tiendaFiltrosProvider);
    final notificador = ref.read(tiendaFiltrosProvider.notifier);
    final productos = ref.watch(productosPublicosProvider).valueOrNull ?? const <ProductoPublico>[];
    final sucursales = ref.watch(sucursalesDeTiendaProvider(filtros.tienda)).valueOrNull ?? const [];
    final temporadas = ref.watch(temporadasDeTiendaProvider(filtros.tienda)).valueOrNull ?? const [];

    // Boutiques: las que tienen prendas en el catalogo.
    final tiendas = <String, ProductoPublico>{};
    for (final p in productos) {
      if (p.tienda.isNotEmpty) tiendas.putIfAbsent(p.tienda, () => p);
    }
    final listaTiendas = tiendas.values.toList()..sort((a, b) => a.tiendaNombre.compareTo(b.tiendaNombre));

    // Para quien: solo las opciones que tienen prendas (unisex cuenta como mujer y hombre).
    final hay = productos.map((p) => p.publico ?? 'unisex').toSet();
    final opcionesPublico = publicos
        .where((o) => o.$1 != 'unisex' && (hay.contains(o.$1) || (hay.contains('unisex') && (o.$1 == 'mujer' || o.$1 == 'hombre'))))
        .toList();

    final categorias = (productos.map((p) => p.categoriaNombre).where((c) => c.isNotEmpty).toSet().toList()..sort());
    final marcas = productos
        .where((p) => (filtros.categoria == null || p.categoriaNombre == filtros.categoria) && (filtros.tienda == null || p.tienda == filtros.tienda))
        .map((p) => p.marcaNombre)
        .where((m) => m.isNotEmpty)
        .toSet()
        .toList()
      ..sort();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(child: Text('Filtros', style: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.w800, color: _marca))),
            GestureDetector(
              onTap: () {
                notificador.limpiarTodo();
                setState(() => _rango = const RangeValues(_precioMin, _precioMax));
              },
              child: Text('Limpiar',
                  style: GoogleFonts.inter(
                      fontSize: 12, fontWeight: FontWeight.w600, color: const Color(0xFF888888), decoration: TextDecoration.underline)),
            ),
          ],
        ),
        const SizedBox(height: 24),
        _Grupo(
          titulo: 'Boutique',
          children: [
            _Opcion(texto: 'Todas las Boutiques', marcada: filtros.tienda == null, onTap: () => notificador.setTienda(null)),
            for (final t in listaTiendas)
              _Opcion(
                marcada: filtros.tienda == t.tienda,
                onTap: () => notificador.setTienda(t.tienda),
                contenido: Row(
                  children: [
                    Container(
                      width: 24,
                      height: 24,
                      clipBehavior: Clip.antiAlias,
                      padding: const EdgeInsets.all(3),
                      decoration: BoxDecoration(color: colorDesdeHex(t.tiendaColor), shape: BoxShape.circle),
                      child: t.tiendaLogo != null && t.tiendaLogo!.isNotEmpty
                          ? ImagenTienda(t.tiendaLogo!)
                          : Center(
                              child: Text(t.tiendaNombre.isEmpty ? '?' : t.tiendaNombre[0].toUpperCase(),
                                  style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800)),
                            ),
                    ),
                    const SizedBox(width: 8),
                    Flexible(child: Text(t.tiendaNombre, style: _estiloOpcion(filtros.tienda == t.tienda))),
                  ],
                ),
              ),
          ],
        ),
        _Grupo(
          titulo: 'Sucursal',
          children: [
            _Opcion(
              marcada: filtros.sucursal == null,
              onTap: () => notificador.setSucursal(null),
              contenido: Text('Todas las Sucursales',
                  style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: _marca)),
            ),
            for (final s in sucursales)
              _Opcion(
                marcada: filtros.sucursal == s.nombre,
                onTap: () => notificador.setSucursal(s.nombre),
                contenido: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(s.nombre, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: _marca)),
                    if (s.direccion.isNotEmpty)
                      Text(s.direccion, style: GoogleFonts.inter(fontSize: 11, color: const Color(0xFF999999))),
                  ],
                ),
              ),
          ],
        ),
        _Grupo(
          titulo: 'Temporada',
          children: [
            _Opcion(texto: 'Todas las Temporadas', marcada: filtros.temporada == null, onTap: () => notificador.setTemporada(null)),
            for (final t in temporadas)
              _Opcion(texto: t.nombre, marcada: filtros.temporada == t.nombre, onTap: () => notificador.setTemporada(t.nombre)),
          ],
        ),
        if (opcionesPublico.length > 1)
          _Grupo(
            titulo: 'Para quién',
            children: [
              _Opcion(texto: 'Todos', marcada: filtros.publico == null, onTap: () => notificador.setPublico(null)),
              for (final o in opcionesPublico)
                _Opcion(texto: o.$2, marcada: filtros.publico == o.$1, onTap: () => notificador.setPublico(o.$1)),
            ],
          ),
        _Grupo(
          titulo: 'Categorias',
          abierto: _categoriasAbiertas,
          onAlternar: () => setState(() => _categoriasAbiertas = !_categoriasAbiertas),
          children: [
            _Opcion(texto: 'Todas', marcada: filtros.categoria == null, onTap: () => notificador.setCategoria(null)),
            for (final c in categorias)
              _Opcion(texto: c, marcada: filtros.categoria == c, onTap: () => notificador.setCategoria(c)),
          ],
        ),
        _Grupo(
          titulo: 'Marcas',
          children: [
            _Opcion(texto: 'Todas las Marcas', marcada: filtros.marcas.isEmpty, onTap: notificador.limpiarMarcas),
            for (final m in marcas)
              _Opcion(texto: m, marcada: filtros.marcas.contains(m), resaltar: false, onTap: () => notificador.toggleMarca(m)),
          ],
        ),
        _Grupo(
          titulo: 'Precio',
          abierto: _precioAbierto,
          onAlternar: () => setState(() => _precioAbierto = !_precioAbierto),
          children: [
            SliderTheme(
              data: SliderTheme.of(context).copyWith(
                trackHeight: 3,
                activeTrackColor: _marca,
                inactiveTrackColor: const Color(0xFFE0E0E0),
                thumbColor: _marca,
                overlayShape: SliderComponentShape.noOverlay,
                rangeThumbShape: const RoundRangeSliderThumbShape(enabledThumbRadius: 8),
              ),
              child: RangeSlider(
                min: _precioMin,
                max: _precioMax,
                values: _rango,
                onChanged: (r) => setState(() => _rango = r),
                onChangeEnd: _aplicarPrecio,
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(child: _CajaPrecio(valor: _rango.start, onCambio: (v) => _aplicarPrecio(RangeValues(v.clamp(_precioMin, _rango.end), _rango.end)))),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  child: Text('—', style: GoogleFonts.inter(color: const Color(0xFF999999))),
                ),
                Expanded(child: _CajaPrecio(valor: _rango.end, onCambio: (v) => _aplicarPrecio(RangeValues(_rango.start, v.clamp(_rango.start, _precioMax))))),
              ],
            ),
          ],
        ),
      ],
    );
  }
}

TextStyle _estiloOpcion(bool activa) => GoogleFonts.inter(
      fontSize: 14,
      fontWeight: activa ? FontWeight.w700 : FontWeight.w400,
      color: activa ? _marca : const Color(0xFF333333),
    );

class _Grupo extends StatelessWidget {
  const _Grupo({required this.titulo, required this.children, this.abierto = true, this.onAlternar});

  final String titulo;
  final List<Widget> children;
  final bool abierto;

  /// Grupos con "×" para contraer (Categorias y Precio, como en la web).
  final VoidCallback? onAlternar;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 20),
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFFE5E5E5)))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(titulo, style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, color: _marca))),
              if (onAlternar != null)
                GestureDetector(
                  onTap: onAlternar,
                  child: Text(abierto ? '×' : '+', style: GoogleFonts.inter(fontSize: 16, color: const Color(0xFF999999))),
                ),
            ],
          ),
          if (abierto) ...[const SizedBox(height: 14), ...children],
        ],
      ),
    );
  }
}

class _Opcion extends StatelessWidget {
  const _Opcion({required this.marcada, required this.onTap, this.texto, this.contenido, this.resaltar = true});

  final bool marcada;
  final VoidCallback onTap;
  final String? texto;
  final Widget? contenido;

  /// Las marcas (seleccion multiple) no se ponen en negrita, como en la web.
  final bool resaltar;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          crossAxisAlignment: contenido is Column ? CrossAxisAlignment.start : CrossAxisAlignment.center,
          children: [
            SizedBox(
              width: 18,
              height: 18,
              child: Checkbox(
                value: marcada,
                onChanged: (_) => onTap(),
                activeColor: _marca,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                visualDensity: VisualDensity.compact,
                side: const BorderSide(color: Color(0xFF767676), width: 1.5),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(child: contenido ?? Text(texto ?? '', style: _estiloOpcion(marcada && resaltar))),
          ],
        ),
      ),
    );
  }
}

class _CajaPrecio extends StatefulWidget {
  const _CajaPrecio({required this.valor, required this.onCambio});

  final double valor;
  final ValueChanged<double> onCambio;

  @override
  State<_CajaPrecio> createState() => _CajaPrecioState();
}

class _CajaPrecioState extends State<_CajaPrecio> {
  late final _ctrl = TextEditingController(text: widget.valor.round().toString());
  final _foco = FocusNode();

  @override
  void didUpdateWidget(covariant _CajaPrecio old) {
    super.didUpdateWidget(old);
    if (!_foco.hasFocus && old.valor != widget.valor) _ctrl.text = widget.valor.round().toString();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _foco.dispose();
    super.dispose();
  }

  void _confirmar() {
    final v = double.tryParse(_ctrl.text.trim());
    if (v != null) widget.onCambio(v);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(border: Border.all(color: const Color(0xFFDDDDDD))),
      child: Row(
        children: [
          Text('Bs', style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF888888))),
          const SizedBox(width: 6),
          Expanded(
            child: TextField(
              controller: _ctrl,
              focusNode: _foco,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              onSubmitted: (_) => _confirmar(),
              onTapOutside: (_) {
                if (_foco.hasFocus) {
                  _foco.unfocus();
                  _confirmar();
                }
              },
              style: GoogleFonts.inter(fontSize: 14, color: _marca),
              decoration: const InputDecoration(
                isDense: true,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                contentPadding: EdgeInsets.symmetric(vertical: 10),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ================================================================== grilla

class _BarraResultados extends StatelessWidget {
  const _BarraResultados({
    required this.cantidad,
    required this.orden,
    required this.onOrden,
    required this.busqueda,
    required this.onQuitarBusqueda,
  });

  final int cantidad;
  final _Orden orden;
  final ValueChanged<_Orden> onOrden;
  final String busqueda;
  final VoidCallback onQuitarBusqueda;

  @override
  Widget build(BuildContext context) {
    const gris = Color(0xFF8A97A3);
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (busqueda.isNotEmpty) ...[
            Row(
              children: [
                Flexible(
                  child: Text('Resultados para «$busqueda»',
                      style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: _marca)),
                ),
                const SizedBox(width: 8),
                GestureDetector(
                  onTap: onQuitarBusqueda,
                  child: Text('Quitar',
                      style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF888888), decoration: TextDecoration.underline)),
                ),
              ],
            ),
            const SizedBox(height: 10),
          ],
          Row(
            children: [
              Expanded(
                child: Text('MOSTRANDO $cantidad RESULTADOS',
                    style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5, color: gris)),
              ),
              PopupMenuButton<_Orden>(
                onSelected: onOrden,
                color: Colors.white,
                shape: const RoundedRectangleBorder(side: BorderSide(color: Color(0xFFE5E5E5))),
                itemBuilder: (_) => [
                  for (final o in _Orden.values)
                    PopupMenuItem(value: o, child: Text(_etiquetasOrden[o]!, style: GoogleFonts.inter(fontSize: 13, color: const Color(0xFF333333)))),
                ],
                child: Row(
                  children: [
                    Text('ORDENAR: ', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: gris)),
                    Text(_etiquetasOrden[orden]!.toUpperCase(),
                        style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, color: _marca)),
                    const Icon(Icons.keyboard_arrow_down, size: 18, color: _marca),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// `.product-tile`: foto 3/4, insignia de agotado y, en el catalogo
/// universal, la boutique que vende la prenda.
class _TarjetaProducto extends StatelessWidget {
  const _TarjetaProducto({required this.producto});

  final ProductoPublico producto;

  @override
  Widget build(BuildContext context) {
    final p = producto;
    return GestureDetector(
      onTap: () => context.push('/producto/${p.id}'),
      child: Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          boxShadow: [BoxShadow(color: Color(0xFFE2E2E0), spreadRadius: 0.5)],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AspectRatio(
              aspectRatio: 3 / 4,
              child: Container(
                color: const Color(0xFFD9D9D6),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (p.imagenPrincipal != null)
                      CachedNetworkImage(imageUrl: p.imagenPrincipal!, fit: BoxFit.cover, errorWidget: (_, _, _) => const SizedBox()),
                    if (p.agotado)
                      Positioned(
                        top: 10,
                        left: 10,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          color: const Color(0xFFB3261E),
                          child: Text('AGOTADO',
                              style: GoogleFonts.inter(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.5)),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (p.tiendaNombre.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Row(
                          children: [
                            if (p.tiendaLogo != null && p.tiendaLogo!.isNotEmpty) ...[
                              ConstrainedBox(
                                constraints: const BoxConstraints(maxWidth: 48, maxHeight: 16),
                                child: ImagenTienda(p.tiendaLogo!, height: 16),
                              ),
                              const SizedBox(width: 6),
                            ],
                            Flexible(
                              child: Text(p.tiendaNombre,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, color: _marca)),
                            ),
                          ],
                        ),
                      ),
                    Text(p.marcaNombre.toUpperCase(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600, letterSpacing: 0.4, color: const Color(0xFF9A9A9A))),
                    const SizedBox(height: 2),
                    Text(p.nombre.toUpperCase(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w800, fontStyle: FontStyle.italic, color: _marca)),
                    const Spacer(),
                    Align(
                      alignment: Alignment.centerRight,
                      child: Text('${p.precio.toStringAsFixed(0)} Bs',
                          style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w800, color: _marca)),
                    ),
                    if (p.temporadaNombre.isNotEmpty)
                      Text(p.temporadaNombre.toUpperCase(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w700, letterSpacing: 0.4, color: const Color(0xFFB2B2B2))),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
