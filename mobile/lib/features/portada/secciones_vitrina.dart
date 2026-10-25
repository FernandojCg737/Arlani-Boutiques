import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_config.dart';
import '../../models/producto_publico.dart';
import '../storefront/catalogo_provider.dart';
import 'estilo_plataforma.dart';
import 'plataforma_data.dart';

// ================================================================= vitrina

/// "Vendé en todos los lugares..." + las tarjetas de las boutiques activas
/// (`vitrina-boutiques` de la web). Atelier lleva tres fotos de su local; cada
/// tienda nueva suma la suya con su color, su logo y la foto de un producto.
class VitrinaBoutiques extends ConsumerStatefulWidget {
  const VitrinaBoutiques({super.key});

  static const frases = [
    'Vendé en todos los lugares donde tus clientes compran.',
    'En línea y en mostrador.',
    'En cada sucursal, aunque se caiga internet.',
    'Con reportes de IA y probador virtual.',
  ];

  @override
  ConsumerState<VitrinaBoutiques> createState() => _VitrinaBoutiquesState();
}

class _VitrinaBoutiquesState extends ConsumerState<VitrinaBoutiques> with SingleTickerProviderStateMixin {
  // En celular cada frase se enciende de a una: ciclo de 12 s, 3 s por frase
  // (`frase-enciende` en vitrina-boutiques.scss).
  late final AnimationController _ciclo = AnimationController(vsync: this, duration: const Duration(seconds: 12))
    ..repeat();

  @override
  void dispose() {
    _ciclo.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ancho = MediaQuery.sizeOf(context).width;
    final tamTitulo = (ancho * 0.046).clamp(35.2, 72.0);

    return Container(
      color: Plataforma.fondo,
      padding: const EdgeInsets.symmetric(vertical: 64),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
            child: AnimatedBuilder(
              animation: _ciclo,
              builder: (context, _) {
                final segundo = _ciclo.value * 12;
                return Text.rich(
                  TextSpan(
                    children: [
                      for (var i = 0; i < VitrinaBoutiques.frases.length; i++)
                        TextSpan(
                          text: '${VitrinaBoutiques.frases[i]} ',
                          style: _estiloFrase(tamTitulo, encendida: segundo >= i * 3 + 0.6 && segundo <= i * 3 + 2.5, ancho: ancho),
                        ),
                      TextSpan(
                        text: 'De tu tienda para toda Bolivia.',
                        style: bricolage(size: tamTitulo, weight: FontWeight.w400, height: 1.04)
                            .copyWith(letterSpacing: -0.03 * tamTitulo),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 40),
          const _TarjetasVitrina(),
        ],
      ),
    );
  }

  TextStyle _estiloFrase(double tam, {required bool encendida, required double ancho}) {
    final base = bricolage(size: tam, weight: FontWeight.w300, color: const Color(0xFF767B85), height: 1.04)
        .copyWith(letterSpacing: -0.03 * tam);
    if (!encendida) return base;
    final degradado = const LinearGradient(colors: [Color(0xFFF7CDBD), Color(0xFFE8806B), Color(0xFFC97BD6)])
        .createShader(Rect.fromLTWH(0, 0, ancho - 2 * Plataforma.margen, tam));
    return GoogleFonts.bricolageGrotesque(
      fontSize: tam,
      fontWeight: FontWeight.w300,
      height: 1.04,
      letterSpacing: -0.03 * tam,
      foreground: Paint()..shader = degradado,
    );
  }
}

class _Tarjeta {
  const _Tarjeta({
    required this.subdominio,
    required this.nombre,
    required this.color,
    required this.imagen,
    this.logo,
    this.ancha = false,
    this.logoRed = false,
  });

  final String subdominio;
  final String nombre;
  final Color color;
  final String imagen;
  final String? logo;
  final bool ancha;
  final bool logoRed;
}

const _tarjetasAtelier = [
  _Tarjeta(subdominio: tiendaOriginal, nombre: 'Atelier Aranier', color: Color(0xFF0F1E20), imagen: 'assets/portada/atelier-local.jpg', logo: '/img/logo.png'),
  _Tarjeta(subdominio: tiendaOriginal, nombre: 'Atelier Aranier', color: Color(0xFF0F1E20), imagen: 'assets/portada/atelier-tienda.jpg', logo: '/img/logo.png', ancha: true),
  _Tarjeta(subdominio: tiendaOriginal, nombre: 'Atelier Aranier', color: Color(0xFF0F1E20), imagen: 'assets/portada/atelier-producto.jpg', logo: '/img/logo.png', ancha: true),
];

class _TarjetasVitrina extends ConsumerWidget {
  const _TarjetasVitrina();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tiendas = ref.watch(tiendasProvider).valueOrNull;
    final productos = ref.watch(productosPublicosProvider).valueOrNull ?? const <ProductoPublico>[];

    final fotos = <String, String>{};
    for (final p in productos) {
      final img = p.imagenPrincipal;
      if (p.tienda.isNotEmpty && img != null && !fotos.containsKey(p.tienda)) fotos[p.tienda] = img;
    }

    final tarjetas = tiendas == null
        ? _tarjetasAtelier
        : [
            for (final t in tiendas)
              if (t.subdominio == tiendaOriginal)
                ..._tarjetasAtelier
              else
                _Tarjeta(
                  subdominio: t.subdominio,
                  nombre: t.nombre,
                  color: t.colorMarca,
                  imagen: fotos[t.subdominio] ?? resolveImageUrl('/img/tienda-hero-poster.jpg'),
                  logo: t.logoUrl,
                  logoRed: t.logoUrl?.startsWith('http') ?? false,
                ),
          ];

    final ancho = MediaQuery.sizeOf(context).width;
    // Las angostas miden 62vw con proporcion 3/4; la fila toma ese alto.
    final alto = ancho * 0.62 * 4 / 3;

    return SizedBox(
      height: alto,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
        itemCount: tarjetas.length,
        separatorBuilder: (_, _) => const SizedBox(width: 16),
        itemBuilder: (context, i) {
          final t = tarjetas[i];
          return SizedBox(width: ancho * (t.ancha ? 0.84 : 0.62), child: _TarjetaVitrina(tarjeta: t));
        },
      ),
    );
  }
}

class _TarjetaVitrina extends StatelessWidget {
  const _TarjetaVitrina({required this.tarjeta});

  final _Tarjeta tarjeta;

  @override
  Widget build(BuildContext context) {
    final foto = tarjeta.imagen.startsWith('assets/')
        ? Image.asset(tarjeta.imagen, fit: BoxFit.cover, alignment: Alignment.topCenter)
        : CachedNetworkImage(imageUrl: tarjeta.imagen, fit: BoxFit.cover, alignment: Alignment.topCenter);

    return Semantics(
      button: true,
      label: 'Visitar ${tarjeta.nombre}, ${enlaceTiendaCorto(tarjeta.subdominio)}',
      child: GestureDetector(
        onTap: () => abrirTienda(context, tarjeta.subdominio),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: Container(
            color: const Color(0xFF1A2233),
            child: Stack(
              fit: StackFit.expand,
              children: [
                foto,
                // En pantallas tactiles el cartel queda fijo abajo: logo y enlace.
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Container(
                    color: tarjeta.color,
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    child: Row(
                      children: [
                        if (tarjeta.logo != null && tarjeta.logo!.isNotEmpty)
                          SizedBox(
                            width: 72,
                            height: 32,
                            child: ImagenTienda(tarjeta.logo!, contorno: tarjeta.logoRed),
                          )
                        else
                          Text(tarjeta.nombre, style: GoogleFonts.inter(color: Colors.white, fontWeight: FontWeight.w800)),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            enlaceTiendaCorto(tarjeta.subdominio),
                            textAlign: TextAlign.right,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: GoogleFonts.inter(color: Colors.white, fontSize: 12.8, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================== promociones

/// "Ofertas en las boutiques de Arlani": productos con descuento de todas las
/// tiendas (los agotados no se ofrecen), cada uno con el logo de su boutique.
class PromocionesBoutiques extends ConsumerWidget {
  const PromocionesBoutiques({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final productos = ref.watch(productosPublicosProvider).valueOrNull ?? const <ProductoPublico>[];
    final promociones = productos.where((p) => p.tieneDescuento && !p.agotado).take(10).toList();
    if (promociones.isEmpty) return const SizedBox.shrink();

    final ancho = MediaQuery.sizeOf(context).width;
    final anchoTarjeta = (ancho * 0.68).clamp(0.0, 280.0);

    return Container(
      color: Plataforma.marfil,
      padding: const EdgeInsets.symmetric(vertical: 64),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('PROMOCIONES', style: antetituloPlataforma(Plataforma.coralOscuro)),
                const SizedBox(height: 12),
                Text(
                  'OFERTAS EN LAS BOUTIQUES DE ARLANI.',
                  style: tituloPlataforma(size: 32, color: Plataforma.noche),
                ),
              ],
            ),
          ),
          const SizedBox(height: 36),
          SizedBox(
            height: anchoTarjeta * 4 / 3 + 72,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
              itemCount: promociones.length,
              separatorBuilder: (_, _) => const SizedBox(width: 16),
              itemBuilder: (context, i) => SizedBox(width: anchoTarjeta, child: _Promo(producto: promociones[i])),
            ),
          ),
        ],
      ),
    );
  }
}

class _Promo extends StatelessWidget {
  const _Promo({required this.producto});

  final ProductoPublico producto;

  String _bs(double v) => v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(2);

  @override
  Widget build(BuildContext context) {
    final p = producto;
    final colorTienda = colorDesdeHex(p.tiendaColor);

    return GestureDetector(
      onTap: () => context.push('/producto/${p.id}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 3 / 4,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Container(
                color: const Color(0xFFE9E5E1),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (p.imagenPrincipal != null) CachedNetworkImage(imageUrl: p.imagenPrincipal!, fit: BoxFit.cover),
                    Positioned(
                      left: 10,
                      top: 10,
                      child: _Pildora(
                        color: Plataforma.coralOscuro,
                        child: Text('-${p.porcentajeDescuento}%',
                            style: GoogleFonts.inter(color: Colors.white, fontSize: 12.8, fontWeight: FontWeight.w700)),
                      ),
                    ),
                    Positioned(
                      left: 10,
                      bottom: 10,
                      right: 10,
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: _Pildora(
                          color: Colors.white.withValues(alpha: 0.92),
                          padding: const EdgeInsets.fromLTRB(6, 5, 10, 5),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (p.tiendaLogo != null && p.tiendaLogo!.isNotEmpty)
                                SizedBox(height: 16, width: 28, child: ImagenTienda(p.tiendaLogo!))
                              else
                                InicialTienda(nombre: p.tiendaNombre, color: colorTienda),
                              const SizedBox(width: 6),
                              Flexible(
                                child: Text(
                                  p.tiendaNombre,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: GoogleFonts.inter(color: Plataforma.noche, fontSize: 11.5, fontWeight: FontWeight.w600),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 10),
          Text(p.nombre,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.inter(color: Plataforma.noche, fontSize: 15.2, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text('${_bs(p.precio)} Bs',
                  style: GoogleFonts.inter(color: Plataforma.coralOscuro, fontSize: 16.8, fontWeight: FontWeight.w700)),
              const SizedBox(width: 8),
              Text('${_bs(p.precioOriginal!)} Bs',
                  style: GoogleFonts.inter(
                      color: Plataforma.gris, fontSize: 13.6, decoration: TextDecoration.lineThrough)),
            ],
          ),
        ],
      ),
    );
  }
}

class _Pildora extends StatelessWidget {
  const _Pildora({required this.color, required this.child, this.padding = const EdgeInsets.symmetric(horizontal: 10, vertical: 5)});

  final Color color;
  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(999)),
      child: child,
    );
  }
}
