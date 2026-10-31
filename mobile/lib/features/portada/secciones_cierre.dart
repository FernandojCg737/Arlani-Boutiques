import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_config.dart';
import 'estilo_plataforma.dart';
import 'plataforma_data.dart';

// ================================================================== precios

/// "Un plan para cada tamaño de boutique" (`precios-planes`): mensual/anual,
/// deslizador de sucursales que ilumina el plan recomendado y las tres
/// tarjetas de planes.
class PreciosPlanes extends StatefulWidget {
  const PreciosPlanes({super.key});

  @override
  State<PreciosPlanes> createState() => _PreciosPlanesState();
}

class _PreciosPlanesState extends State<PreciosPlanes> {
  bool _anual = false;
  int _sucursales = 2;

  @override
  Widget build(BuildContext context) {
    final recomendado = planParaSucursales(_sucursales).id;

    return Container(
      color: Plataforma.fondo,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(0, 0.24),
            radius: 0.75,
            colors: [Color(0x29E8806B), Color(0x00E8806B)],
            stops: [0, 0.7],
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 72),
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
                child: Column(
                  children: [
                    Text('PRECIOS', style: antetituloPlataforma(Plataforma.oro)),
                    const SizedBox(height: 14),
                    Text('UN PLAN PARA CADA TAMAÑO DE BOUTIQUE.',
                        textAlign: TextAlign.center, style: tituloPlataforma(size: 35.2)),
                    const SizedBox(height: 18),
                    Text(
                      'Sin costo de instalación. Cambiás de plan cuando quieras.',
                      textAlign: TextAlign.center,
                      style: GoogleFonts.inter(fontSize: 16, color: Colors.white.withValues(alpha: 0.6)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 44),
              _SelectorPeriodo(anual: _anual, onCambio: (v) => setState(() => _anual = v)),
              const SizedBox(height: 28),
              _DeslizadorSucursales(valor: _sucursales, onCambio: (v) => setState(() => _sucursales = v)),
              const SizedBox(height: 48),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
                child: Column(
                  children: [
                    for (final plan in planesPlataforma) ...[
                      _TarjetaPlan(plan: plan, anual: _anual, recomendado: plan.id == recomendado),
                      const SizedBox(height: 20),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SelectorPeriodo extends StatelessWidget {
  const _SelectorPeriodo({required this.anual, required this.onCambio});

  final bool anual;
  final ValueChanged<bool> onCambio;

  @override
  Widget build(BuildContext context) {
    final ancho = (MediaQuery.sizeOf(context).width - 2 * Plataforma.margen).clamp(0.0, 330.0);

    Widget boton(String texto, bool esAnual) {
      final activo = anual == esAnual;
      return Expanded(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onCambio(esAnual),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                AnimatedDefaultTextStyle(
                  duration: const Duration(milliseconds: 250),
                  style: GoogleFonts.inter(
                    fontSize: 14.4,
                    fontWeight: FontWeight.w600,
                    color: activo ? Plataforma.fondo : Colors.white.withValues(alpha: 0.7),
                  ),
                  child: Text(texto),
                ),
                if (esAnual) ...[
                  const SizedBox(width: 8),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: activo ? Plataforma.coral : Plataforma.coral.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text('2 meses gratis',
                        style: GoogleFonts.inter(fontSize: 11.2, color: activo ? Colors.white : Plataforma.oro)),
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    }

    return Container(
      width: ancho,
      padding: const EdgeInsets.all(5),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
        color: Colors.white.withValues(alpha: 0.04),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: AnimatedAlign(
              duration: const Duration(milliseconds: 350),
              curve: const Cubic(0.16, 1, 0.3, 1),
              alignment: anual ? Alignment.centerRight : Alignment.centerLeft,
              child: FractionallySizedBox(
                widthFactor: 0.5,
                heightFactor: 1,
                child: Container(decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(999))),
              ),
            ),
          ),
          Row(children: [boton('Mensual', false), boton('Anual', true)]),
        ],
      ),
    );
  }
}

class _DeslizadorSucursales extends StatelessWidget {
  const _DeslizadorSucursales({required this.valor, required this.onCambio});

  final int valor;
  final ValueChanged<int> onCambio;

  @override
  Widget build(BuildContext context) {
    final ancho = (MediaQuery.sizeOf(context).width - 2 * Plataforma.margen).clamp(0.0, 320.0);
    return SizedBox(
      width: ancho,
      child: Column(
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Expanded(
                child: Text('¿Cuántas sucursales tenés?',
                    style: GoogleFonts.inter(fontSize: 14.4, color: Colors.white.withValues(alpha: 0.75))),
              ),
              Text('$valor', style: bricolage(size: 24, weight: FontWeight.w500)),
            ],
          ),
          const SizedBox(height: 4),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              trackHeight: 6,
              activeTrackColor: Plataforma.coral,
              inactiveTrackColor: Colors.white.withValues(alpha: 0.14),
              thumbShape: const _PulgarCoral(),
              overlayShape: SliderComponentShape.noOverlay,
              tickMarkShape: SliderTickMarkShape.noTickMark,
              trackShape: const RoundedRectSliderTrackShape(),
            ),
            child: Slider(
              min: 1,
              max: maxSucursalesPlataforma.toDouble(),
              divisions: maxSucursalesPlataforma - 1,
              value: valor.toDouble(),
              onChanged: (v) => onCambio(v.round()),
            ),
          ),
        ],
      ),
    );
  }
}

/// Pulgar blanco con borde coral y halo (`::-webkit-slider-thumb`).
class _PulgarCoral extends SliderComponentShape {
  const _PulgarCoral();

  @override
  Size getPreferredSize(bool isEnabled, bool isDiscrete) => const Size(34, 34);

  @override
  void paint(
    PaintingContext context,
    Offset center, {
    required Animation<double> activationAnimation,
    required Animation<double> enableAnimation,
    required bool isDiscrete,
    required TextPainter labelPainter,
    required RenderBox parentBox,
    required SliderThemeData sliderTheme,
    required TextDirection textDirection,
    required double value,
    required double textScaleFactor,
    required Size sizeWithOverflow,
  }) {
    final canvas = context.canvas;
    canvas.drawCircle(center, 17, Paint()..color = Plataforma.coral.withValues(alpha: 0.2));
    canvas.drawCircle(center, 11, Paint()..color = Plataforma.coral);
    canvas.drawCircle(center, 7, Paint()..color = Colors.white);
  }
}

class _TarjetaPlan extends StatelessWidget {
  const _TarjetaPlan({required this.plan, required this.anual, required this.recomendado});

  final PlanPlataforma plan;
  final bool anual;
  final bool recomendado;

  String _miles(int n) => n.toString().replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => '.');

  @override
  Widget build(BuildContext context) {
    final monto = plan.precioPorMes(anual);

    return Stack(
      clipBehavior: Clip.none,
      children: [
        AnimatedContainer(
          duration: const Duration(milliseconds: 450),
          curve: const Cubic(0.16, 1, 0.3, 1),
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(28, 32, 28, 30),
          decoration: BoxDecoration(
            color: Plataforma.tarjeta,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: recomendado ? Plataforma.oro.withValues(alpha: 0.55) : Colors.white.withValues(alpha: 0.08)),
            boxShadow: recomendado
                ? [
                    BoxShadow(color: Plataforma.oro.withValues(alpha: 0.25), spreadRadius: 1),
                    BoxShadow(color: Plataforma.coral.withValues(alpha: 0.6), blurRadius: 80, spreadRadius: -30, offset: const Offset(0, 30)),
                  ]
                : null,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(plan.nombre, style: bricolage(size: 24, weight: FontWeight.w500)),
              const SizedBox(height: 8),
              Text(plan.resumen, style: GoogleFonts.inter(fontSize: 14.4, height: 1.45, color: Colors.white.withValues(alpha: 0.6))),
              const SizedBox(height: 22),
              if (plan.esPrueba)
                Text('Gratis', style: bricolage(size: 54.4, height: 1).copyWith(letterSpacing: -2.2))
              else
                Row(
                  crossAxisAlignment: CrossAxisAlignment.baseline,
                  textBaseline: TextBaseline.alphabetic,
                  children: [
                    Text('Bs',
                        style: GoogleFonts.inter(fontSize: 17.6, fontWeight: FontWeight.w600, color: Colors.white.withValues(alpha: 0.7))),
                    const SizedBox(width: 6),
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 450),
                      transitionBuilder: (hijo, anim) => FadeTransition(
                        opacity: anim,
                        child: SlideTransition(position: Tween(begin: const Offset(0, 0.4), end: Offset.zero).animate(anim), child: hijo),
                      ),
                      child: Text('$monto', key: ValueKey(monto), style: bricolage(size: 54.4, height: 1).copyWith(letterSpacing: -2.2)),
                    ),
                    const SizedBox(width: 6),
                    Text('/ mes', style: GoogleFonts.inter(fontSize: 15.2, color: Colors.white.withValues(alpha: 0.6))),
                  ],
                ),
              const SizedBox(height: 8),
              Text(
                plan.esPrueba
                    ? '${plan.diasPrueba} días de prueba, sin tarjeta'
                    : anual
                        ? 'Bs ${_miles(plan.precioAnual)} al año'
                        : 'Facturación mensual',
                style: GoogleFonts.inter(fontSize: 12.8, color: Colors.white.withValues(alpha: 0.5)),
              ),
              const SizedBox(height: 24),
              _BotonPlan(
                texto: plan.esPrueba ? 'Probar gratis' : 'Elegir ${plan.nombre}',
                lleno: recomendado,
                onTap: () => abrirEmpezar(context, plan: plan.id, periodo: anual ? 'anual' : 'mensual'),
              ),
              const SizedBox(height: 26),
              Container(
                padding: const EdgeInsets.only(top: 24),
                decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.08)))),
                child: Column(
                  children: [
                    for (final item in plan.incluye) _Incluye(texto: item),
                    for (final item in plan.noIncluye) _Incluye(texto: item, falta: true),
                  ],
                ),
              ),
            ],
          ),
        ),
        if (recomendado)
          Positioned(
            top: -13,
            left: 28,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
              decoration: BoxDecoration(gradient: Plataforma.degradadoCoral, borderRadius: BorderRadius.circular(999)),
              child: Text('Recomendado para vos',
                  style: GoogleFonts.inter(color: Colors.white, fontSize: 11.5, fontWeight: FontWeight.w700)),
            ),
          ),
      ],
    );
  }
}

class _BotonPlan extends StatelessWidget {
  const _BotonPlan({required this.texto, required this.lleno, required this.onTap});

  final String texto;
  final bool lleno;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onTap,
        child: Ink(
          padding: const EdgeInsets.symmetric(vertical: 15),
          decoration: BoxDecoration(
            gradient: lleno ? Plataforma.degradadoCoral : null,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: lleno ? Colors.transparent : Colors.white.withValues(alpha: 0.25)),
          ),
          child: Center(
            child: Text(texto, style: GoogleFonts.inter(color: Colors.white, fontSize: 15.2, fontWeight: FontWeight.w700)),
          ),
        ),
      ),
    );
  }
}

class _Incluye extends StatelessWidget {
  const _Incluye({required this.texto, this.falta = false});

  final String texto;
  final bool falta;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Icon(falta ? Icons.close : Icons.check, size: 17, color: falta ? Colors.white.withValues(alpha: 0.35) : Plataforma.oro),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              texto,
              style: GoogleFonts.inter(
                fontSize: 14.1,
                height: 1.4,
                color: falta ? Colors.white.withValues(alpha: 0.4) : Colors.white.withValues(alpha: 0.85),
                decoration: falta ? TextDecoration.lineThrough : null,
                decorationColor: Colors.white.withValues(alpha: 0.25),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================ llamado final

/// "Tu boutique, lista para vender hoy." (`cta-final`).
class CtaFinal extends StatelessWidget {
  const CtaFinal({super.key, required this.onVerPlanes});

  final VoidCallback onVerPlanes;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Plataforma.marfil,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(0.76, 0),
            radius: 0.9,
            colors: [Color(0x38E8806B), Color(0x00E8806B)],
            stops: [0, 0.7],
          ),
        ),
        child: Stack(
          clipBehavior: Clip.hardEdge,
          children: [
            Positioned(
              right: -30,
              bottom: -40,
              child: Opacity(
                opacity: 0.18,
                child: Transform.rotate(angle: -0.21, child: Image.asset('assets/portada/arlani-icono-512.png', width: 160)),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen, vertical: 48),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text.rich(
                    TextSpan(
                      text: 'TU BOUTIQUE, LISTA PARA VENDER ',
                      children: [TextSpan(text: 'HOY.', style: TextStyle(color: Plataforma.coralOscuro))],
                    ),
                    style: tituloPlataforma(size: 35.2, color: Plataforma.noche),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Elegí un plan, cargá tus prendas y abrí tu tienda. Nosotros nos encargamos del resto.',
                    style: GoogleFonts.inter(fontSize: 16.3, height: 1.55, color: Plataforma.gris),
                  ),
                  const SizedBox(height: 28),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      _BotonPildora(texto: 'Crear mi boutique', lleno: true, onTap: () => abrirEmpezar(context)),
                      _BotonPildora(texto: 'Ver planes', onTap: onVerPlanes),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BotonPildora extends StatelessWidget {
  const _BotonPildora({required this.texto, required this.onTap, this.lleno = false});

  final String texto;
  final VoidCallback onTap;
  final bool lleno;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: lleno ? Plataforma.noche : Colors.transparent,
      shape: StadiumBorder(side: BorderSide(color: lleno ? Plataforma.noche : Plataforma.noche.withValues(alpha: 0.25), width: 1.5)),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 14),
          child: Text(texto,
              style: GoogleFonts.inter(fontSize: 15.2, fontWeight: FontWeight.w700, color: lleno ? Colors.white : Plataforma.noche)),
        ),
      ),
    );
  }
}

// ======================================================== cinta de logos

/// "Boutiques/Stores": los logos de las tiendas girando sin fin
/// (`carrusel-boutiques`). Cada logo lleva al catalogo de su boutique.
class CarruselBoutiques extends ConsumerStatefulWidget {
  const CarruselBoutiques({super.key});

  @override
  ConsumerState<CarruselBoutiques> createState() => _CarruselBoutiquesState();
}

class _CarruselBoutiquesState extends ConsumerState<CarruselBoutiques> with SingleTickerProviderStateMixin {
  late final AnimationController _cinta = AnimationController(vsync: this, duration: const Duration(seconds: 40))..repeat();

  // Cada mitad de la cinta tiene al menos 8 logos, para llenar la pantalla.
  static const _minimoPorVuelta = 8;
  static const _anchoLogo = 216.0; // 160 de logo + 28 a cada lado

  @override
  void dispose() {
    _cinta.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tiendas = ref.watch(tiendasProvider).valueOrNull ??
        const [TiendaResumen(id: 1, nombre: 'Atelier Aranier', subdominio: tiendaOriginal, colorMarca: Plataforma.azulNoche, logoUrl: '/img/logo.png')];
    if (tiendas.isEmpty) return const SizedBox.shrink();

    final vuelta = <TiendaResumen>[];
    while (vuelta.length < _minimoPorVuelta) {
      vuelta.addAll(tiendas);
    }
    final cinta = [...vuelta, ...vuelta];
    final mitad = vuelta.length * _anchoLogo;

    return Container(
      color: Plataforma.fondo,
      padding: const EdgeInsets.only(top: 40, bottom: 8),
      child: Column(
        children: [
          Text('BOUTIQUES/STORES', style: antetituloPlataforma(Plataforma.oro).copyWith(letterSpacing: 1.8)),
          const SizedBox(height: 24),
          SizedBox(
            height: 64,
            child: ShaderMask(
              blendMode: BlendMode.dstIn,
              shaderCallback: (rect) => const LinearGradient(
                colors: [Colors.transparent, Colors.black, Colors.black, Colors.transparent],
                stops: [0, 0.1, 0.9, 1],
              ).createShader(rect),
              child: ClipRect(
                child: AnimatedBuilder(
                  animation: _cinta,
                  builder: (context, hijo) => OverflowBox(
                    alignment: Alignment.centerLeft,
                    maxWidth: double.infinity,
                    child: Transform.translate(offset: Offset(-_cinta.value * mitad, 0), child: hijo),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [for (final t in cinta) _LogoCinta(tienda: t)],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

const _grises = ColorFilter.matrix([
  0.2126, 0.7152, 0.0722, 0, 0, //
  0.2126, 0.7152, 0.0722, 0, 0, //
  0.2126, 0.7152, 0.0722, 0, 0, //
  0, 0, 0, 1, 0,
]);

class _LogoCinta extends StatelessWidget {
  const _LogoCinta({required this.tienda});

  final TiendaResumen tienda;

  @override
  Widget build(BuildContext context) {
    final logo = tienda.logoUrl;
    return GestureDetector(
      onTap: () => abrirTienda(context, tienda.subdominio),
      child: SizedBox(
        width: _CarruselBoutiquesState._anchoLogo,
        child: Center(
          child: Opacity(
            opacity: 0.6,
            child: ColorFiltered(
              colorFilter: _grises,
              child: logo != null && logo.isNotEmpty
                  ? ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 48, maxWidth: 160),
                      child: ImagenTienda(logo, contorno: logo.startsWith('http')),
                    )
                  : Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        InicialTienda(nombre: tienda.nombre, color: tienda.colorMarca, size: 28),
                        const SizedBox(width: 10),
                        Flexible(
                          child: Text(tienda.nombre.toUpperCase(),
                              overflow: TextOverflow.ellipsis,
                              style: GoogleFonts.inter(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: 0.6)),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================ pie de pagina

/// Pie de la plataforma (`footer-plataforma`).
class PiePlataforma extends StatelessWidget {
  const PiePlataforma({super.key, required this.onIrA});

  final void Function(SeccionPortada) onIrA;

  Future<void> _abrirWeb(String ruta) =>
      launchUrl(Uri.parse('$webAssetsBaseUrl$ruta'), mode: LaunchMode.externalApplication);

  @override
  Widget build(BuildContext context) {
    final enlace = GoogleFonts.inter(fontSize: 14.7, color: Colors.white.withValues(alpha: 0.78));

    Widget columna(String titulo, List<(String, VoidCallback)> enlaces) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titulo.toUpperCase(), style: antetituloPlataforma(Plataforma.oro).copyWith(fontSize: 12)),
            const SizedBox(height: 16),
            for (final e in enlaces)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: GestureDetector(onTap: e.$2, child: Text(e.$1, style: enlace)),
              ),
          ],
        );

    return Container(
      color: Plataforma.fondo,
      padding: const EdgeInsets.fromLTRB(Plataforma.margen, 56, Plataforma.margen, 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GestureDetector(
            onTap: () => onIrA(SeccionPortada.inicio),
            child: Image.asset('assets/portada/arlani-logo-encabezado.png', height: 60),
          ),
          const SizedBox(height: 18),
          Text(
            'La plataforma para que las boutiques de Bolivia vendan en línea y en mostrador, en todas sus sucursales.',
            style: GoogleFonts.inter(fontSize: 14.7, height: 1.5, color: Colors.white.withValues(alpha: 0.6)),
          ),
          const SizedBox(height: 40),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: columna('Plataforma', [
                  ('Por qué Arlani', () => onIrA(SeccionPortada.porQue)),
                  ('Funciones', () => onIrA(SeccionPortada.funciones)),
                  ('Precios', () => onIrA(SeccionPortada.precios)),
                ]),
              ),
              Expanded(
                child: columna('Para boutiques', [
                  ('Crear mi boutique', () => abrirEmpezar(context)),
                  ('Iniciar sesión', () => context.push('/login')),
                ]),
              ),
            ],
          ),
          const SizedBox(height: 28),
          columna('Boutiques', [
            ('Ver todas', () => onIrA(SeccionPortada.boutiques)),
            ('Promociones', () => onIrA(SeccionPortada.promociones)),
          ]),
          Container(
            margin: const EdgeInsets.only(top: 28),
            padding: const EdgeInsets.only(top: 20),
            decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.08)))),
            child: Wrap(
              spacing: 20,
              runSpacing: 8,
              children: [
                Text('© ${DateTime.now().year} Arlani Boutiques. Todos los derechos reservados.',
                    style: GoogleFonts.inter(fontSize: 12.8, color: Colors.white.withValues(alpha: 0.5))),
                GestureDetector(
                  onTap: () => _abrirWeb('/privacidad'),
                  child: Text('Privacidad', style: GoogleFonts.inter(fontSize: 12.8, color: Colors.white.withValues(alpha: 0.7))),
                ),
                GestureDetector(
                  onTap: () => _abrirWeb('/terminos'),
                  child: Text('Términos', style: GoogleFonts.inter(fontSize: 12.8, color: Colors.white.withValues(alpha: 0.7))),
                ),
                Text('Hecho en Bolivia', style: GoogleFonts.inter(fontSize: 12.8, color: Colors.white.withValues(alpha: 0.5))),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
