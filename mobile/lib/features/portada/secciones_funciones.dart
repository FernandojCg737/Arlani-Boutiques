import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'estilo_plataforma.dart';
import 'plataforma_data.dart';

/// "Llegá más lejos. Sin perder el control de nada." (`funciones-plataforma`):
/// tres tarjetas animadas — tu tienda con tu marca, el panel de todas las
/// sucursales y las ventas sin internet. Las animaciones corren solo mientras
/// la tarjeta esta en pantalla.
class FuncionesPlataforma extends StatelessWidget {
  const FuncionesPlataforma({super.key});

  @override
  Widget build(BuildContext context) {
    final linkStyle = GoogleFonts.inter(
      color: Colors.white.withValues(alpha: 0.85),
      fontSize: 14.7,
      height: 1.55,
      decoration: TextDecoration.underline,
      decorationColor: Colors.white.withValues(alpha: 0.85),
    );

    return Container(
      color: Plataforma.fondo,
      padding: const EdgeInsets.fromLTRB(Plataforma.margen, 24, Plataforma.margen, 72),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('LLEGÁ MÁS LEJOS.\nSIN PERDER EL CONTROL DE NADA.', style: tituloPlataforma(size: 32)),
          const SizedBox(height: 36),
          _Funcion(
            lienzo: const _LienzoTienda(),
            titulo: 'Tu tienda online,\ncon tu marca',
            texto: Text.rich(
              TextSpan(
                children: [
                  const TextSpan(text: 'Catálogo, carrito, reservas y probador virtual listos desde el primer día. '),
                  WidgetSpan(
                    alignment: PlaceholderAlignment.baseline,
                    baseline: TextBaseline.alphabetic,
                    child: GestureDetector(
                      onTap: () => abrirTienda(context, tiendaOriginal),
                      child: Text('Mirá una tienda real', style: linkStyle),
                    ),
                  ),
                  const TextSpan(text: '.'),
                ],
              ),
              style: _estiloParrafo,
            ),
          ),
          const SizedBox(height: 40),
          const _Funcion(
            lienzo: _LienzoPanel(),
            titulo: 'Todas tus sucursales en un panel',
            texto: Text(
              'Inventario, ventas, reservas y empleados de cada sucursal. Lo ves todo junto o por separado, desde donde estés.',
              style: _estiloParrafo,
            ),
          ),
          const SizedBox(height: 40),
          const _Funcion(
            lienzo: _LienzoOffline(),
            titulo: 'Vendé aunque se caiga internet',
            texto: Text(
              'La caja y la app guardan cada venta sin conexión y la sincronizan solas cuando vuelve la señal.',
              style: _estiloParrafo,
            ),
          ),
        ],
      ),
    );
  }
}

const _estiloParrafo = TextStyle(color: Color(0x9EFFFFFF), fontSize: 14.7, height: 1.55);

class _Funcion extends StatelessWidget {
  const _Funcion({required this.lienzo, required this.titulo, required this.texto});

  final Widget lienzo;
  final String titulo;
  final Widget texto;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          height: 340,
          width: double.infinity,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
            color: Plataforma.lienzo,
          ),
          child: DecoratedBox(
            decoration: const BoxDecoration(
              gradient: RadialGradient(
                radius: 0.9,
                colors: [Color(0x593E4C6D), Color(0x000E1524)],
                stops: [0, 0.7],
              ),
            ),
            child: lienzo,
          ),
        ),
        const SizedBox(height: 24),
        Text(titulo, style: GoogleFonts.inter(color: Colors.white, fontSize: 19.2, fontWeight: FontWeight.w600, height: 1.3)),
        const SizedBox(height: 10),
        texto,
      ],
    );
  }
}

/// Animacion que solo corre mientras se ve (`.funciones--activa` en la web).
mixin _AnimaEnVista<T extends StatefulWidget> on State<T>, SingleTickerProviderStateMixin<T> {
  late final AnimationController reloj = AnimationController(vsync: this, duration: const Duration(seconds: 84));
  final _clave = UniqueKey();

  /// Segundos transcurridos (el reloj da la vuelta cada 84 s: multiplo de
  /// todos los ciclos de la seccion).
  double get segundos => reloj.value * 84;

  Widget enVista(WidgetBuilder builder) => VisibilityDetector(
        key: _clave,
        onVisibilityChanged: (info) {
          if (!mounted) return;
          if (info.visibleFraction > 0.15) {
            if (!reloj.isAnimating) reloj.repeat();
          } else {
            reloj.stop();
          }
        },
        child: AnimatedBuilder(animation: reloj, builder: (context, _) => builder(context)),
      );

  @override
  void dispose() {
    reloj.dispose();
    super.dispose();
  }
}

double _ola(double segundos, double periodo, {double desfase = 0}) =>
    (1 - math.cos(2 * math.pi * ((segundos + desfase) / periodo))) / 2;

// --------------------------------------------------------------- anillos

class _Anillos extends CustomPainter {
  _Anillos({required this.centro, this.suaves = false, this.giro});

  final Offset Function(Size) centro;
  final bool suaves;

  /// Barrido del panel: una cola coral que recorre los anillos (radianes).
  final double? giro;

  static const radios = [110.0, 195.0, 290.0];

  @override
  void paint(Canvas canvas, Size size) {
    final c = centro(size);
    final linea = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = Plataforma.oro.withValues(alpha: suaves ? 0.08 : 0.16);
    for (final r in radios) {
      canvas.drawCircle(c, r, linea);
    }
    if (giro == null) return;
    for (final r in radios) {
      final rect = Rect.fromCircle(center: c, radius: r);
      final barrido = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..shader = SweepGradient(
          colors: const [Color(0x00E8806B), Color(0x00E8806B), Color(0x47E8806B)],
          stops: const [0, 250 / 360, 1],
          transform: GradientRotation(giro!),
        ).createShader(rect);
      canvas.drawCircle(c, r, barrido);
    }
  }

  @override
  bool shouldRepaint(covariant _Anillos old) => old.giro != giro;
}

// ------------------------------------------------- 1. tienda con tu marca

class _LienzoTienda extends StatefulWidget {
  const _LienzoTienda();

  @override
  State<_LienzoTienda> createState() => _LienzoTiendaState();
}

class _LienzoTiendaState extends State<_LienzoTienda> with SingleTickerProviderStateMixin, _AnimaEnVista {
  static const _muestras = [Color(0xFF203C40), Color(0xFFE8806B), Color(0xFFF7F4F2)];

  @override
  Widget build(BuildContext context) {
    return enVista(
      (context) => LayoutBuilder(
        builder: (context, c) {
          final s = segundos;
          final anchoMaqueta = c.maxWidth * 1.6;
          final altoMaqueta = anchoMaqueta * 917 / 1200;
          final respira = _ola(s, 4);
          final flota = -6 * _ola(s, 5);
          final elegida = (s % 6) ~/ 2;

          return Stack(
            clipBehavior: Clip.hardEdge,
            children: [
              Positioned.fill(
                child: CustomPaint(painter: _Anillos(centro: (size) => Offset(0, size.height), suaves: true)),
              ),
              Positioned(
                left: c.maxWidth * 0.15,
                top: c.maxHeight * 0.12,
                width: anchoMaqueta,
                height: altoMaqueta,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Positioned.fill(
                      child: Container(
                        decoration: const BoxDecoration(
                          borderRadius: BorderRadius.horizontal(left: Radius.circular(8)),
                          boxShadow: [BoxShadow(color: Color(0xB3000000), offset: Offset(0, 30), blurRadius: 60, spreadRadius: -20)],
                        ),
                        child: ClipRRect(
                          borderRadius: const BorderRadius.horizontal(left: Radius.circular(8)),
                          child: Image.asset('assets/portada/atelier-tienda.jpg', fit: BoxFit.cover),
                        ),
                      ),
                    ),
                    // Recuadro de edicion sobre el titulo de la tienda.
                    Positioned(
                      left: anchoMaqueta * 0.33,
                      top: altoMaqueta * 0.16,
                      width: anchoMaqueta * 0.34,
                      height: altoMaqueta * 0.16,
                      child: Stack(
                        clipBehavior: Clip.none,
                        children: [
                          Positioned.fill(
                            child: Container(
                              decoration: BoxDecoration(
                                border: Border.all(color: Plataforma.coral, width: 2),
                                borderRadius: BorderRadius.circular(3),
                                boxShadow: [
                                  BoxShadow(color: Plataforma.coral.withValues(alpha: 0.18 * respira), spreadRadius: 6 * respira),
                                ],
                              ),
                            ),
                          ),
                          Positioned(
                            left: -2,
                            bottom: altoMaqueta * 0.16,
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                              decoration: const BoxDecoration(
                                color: Plataforma.coral,
                                borderRadius: BorderRadius.vertical(top: Radius.circular(4)),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.notes, size: 11, color: Colors.white),
                                  const SizedBox(width: 4),
                                  Text('Tu marca', style: GoogleFonts.inter(color: Colors.white, fontSize: 10.9, fontWeight: FontWeight.w600)),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    // "Tus colores": pastilla blanca que flota, con la muestra elegida que va rotando.
                    Positioned(
                      left: anchoMaqueta * 0.26,
                      top: altoMaqueta * 0.46 + flota,
                      child: Container(
                        padding: const EdgeInsets.fromLTRB(10, 8, 12, 8),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(999),
                          boxShadow: const [BoxShadow(color: Color(0x8C000000), offset: Offset(0, 12), blurRadius: 30, spreadRadius: -8)],
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            for (var i = 0; i < _muestras.length; i++) ...[
                              Container(
                                width: 16,
                                height: 16,
                                decoration: BoxDecoration(
                                  color: _muestras[i],
                                  shape: BoxShape.circle,
                                  border: Border.all(color: Colors.black.withValues(alpha: 0.15)),
                                  boxShadow: i == elegida
                                      ? const [
                                          BoxShadow(color: Colors.white, spreadRadius: 2),
                                          BoxShadow(color: Plataforma.coral, spreadRadius: 4),
                                        ]
                                      : null,
                                ),
                              ),
                              const SizedBox(width: 6),
                            ],
                            Text('Tus colores', style: GoogleFonts.inter(color: Plataforma.tinta, fontSize: 12.5, fontWeight: FontWeight.w600)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

// ------------------------------------------- 2. panel de todas las sucursales

class _LienzoPanel extends StatefulWidget {
  const _LienzoPanel();

  @override
  State<_LienzoPanel> createState() => _LienzoPanelState();
}

class _LienzoPanelState extends State<_LienzoPanel> with SingleTickerProviderStateMixin, _AnimaEnVista {
  // Etiquetas que orbitan en los anillos (posiciones en % del lienzo).
  static const _modulos = [
    ('Inventario', 50.0, 9.0),
    ('Ventas', 84.0, 26.0),
    ('Reservas', 86.0, 70.0),
    ('Pagos', 62.0, 90.0),
    ('Empleados', 24.0, 88.0),
    ('Sucursales', 13.0, 50.0),
    ('Reportes IA', 22.0, 16.0),
  ];

  /// `modulo-enciende`: ciclo de 14 s, cada uno 2 s despues del anterior.
  double _encendido(double s, int i) {
    final t = (((s - i * 2) % 14) + 14) % 14 / 14;
    if (t < 0.04) return t / 0.04;
    if (t < 0.16) return 1;
    if (t < 0.22) return 1 - (t - 0.16) / 0.06;
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    return enVista(
      (context) => LayoutBuilder(
        builder: (context, c) {
          final s = segundos;
          final late = _ola(s, 5);
          final escala = 1 + 0.08 * late;
          final separacion = c.maxWidth >= 600 ? 0.01 : 0.0074;

          return Stack(
            clipBehavior: Clip.hardEdge,
            alignment: Alignment.center,
            children: [
              Positioned.fill(
                child: CustomPaint(
                  painter: _Anillos(centro: (size) => size.center(Offset.zero), giro: 2 * math.pi * (s % 9) / 9),
                ),
              ),
              Opacity(
                opacity: 0.85 + 0.15 * late,
                child: Transform.scale(
                  scale: escala,
                  child: Container(
                    width: 210,
                    height: 210,
                    decoration: const BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        colors: [Color(0x6BE8806B), Color(0x1FE8806B), Color(0x00E8806B)],
                        stops: [0, 0.45, 0.7],
                      ),
                    ),
                  ),
                ),
              ),
              for (var i = 0; i < _modulos.length; i++)
                Positioned(
                  left: c.maxWidth * (0.5 + (_modulos[i].$2 - 50) * separacion),
                  top: c.maxHeight * (0.5 + (_modulos[i].$3 - 50) * 0.01),
                  child: FractionalTranslation(
                    translation: const Offset(-0.5, -0.5),
                    child: _Modulo(nombre: _modulos[i].$1, encendido: _encendido(s, i)),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _Modulo extends StatelessWidget {
  const _Modulo({required this.nombre, required this.encendido});

  final String nombre;
  final double encendido;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 7),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: const Color(0xBF0B111D),
        border: Border.all(
          color: Color.lerp(Colors.white.withValues(alpha: 0.1), Plataforma.oro.withValues(alpha: 0.65), encendido)!,
        ),
        boxShadow: encendido > 0
            ? [BoxShadow(color: Plataforma.coral.withValues(alpha: 0.55 * encendido), blurRadius: 24, spreadRadius: -4)]
            : null,
      ),
      child: Text(
        nombre,
        style: GoogleFonts.inter(
          fontSize: 12.2,
          fontWeight: FontWeight.w600,
          color: Color.lerp(Colors.white.withValues(alpha: 0.38), Colors.white, encendido),
        ),
      ),
    );
  }
}

// --------------------------------------------------- 3. ventas sin internet

class _LienzoOffline extends StatefulWidget {
  const _LienzoOffline();

  @override
  State<_LienzoOffline> createState() => _LienzoOfflineState();
}

class _LienzoOfflineState extends State<_LienzoOffline> with SingleTickerProviderStateMixin, _AnimaEnVista {
  /// `estado-sin` / `estado-ok`: 8 s, se cruzan entre el 45% y el 52%.
  double _sinInternet(double s) {
    final t = (s % 8) / 8;
    if (t < 0.45) return 1;
    if (t < 0.52) return 1 - (t - 0.45) / 0.07;
    if (t < 0.95) return 0;
    return (t - 0.95) / 0.05;
  }

  @override
  Widget build(BuildContext context) {
    return enVista(
      (context) => LayoutBuilder(
        builder: (context, c) {
          final s = segundos;
          final sin = _sinInternet(s);

          Widget baldosa({required IconData icono, required String texto, required double desfase}) => Transform.translate(
                offset: Offset(0, -7 * _ola(s, 6, desfase: desfase)),
                child: Container(
                  width: 66,
                  height: 66,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
                    color: Colors.white.withValues(alpha: 0.04),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(icono, size: 24, color: Colors.white.withValues(alpha: 0.85)),
                      const SizedBox(height: 4),
                      Text(texto,
                          style: GoogleFonts.inter(fontSize: 10.6, fontWeight: FontWeight.w600, color: Colors.white.withValues(alpha: 0.6))),
                    ],
                  ),
                ),
              );

          return Stack(
            clipBehavior: Clip.hardEdge,
            children: [
              Positioned.fill(
                child: CustomPaint(painter: _Anillos(centro: (size) => size.center(Offset.zero), suaves: true)),
              ),
              Positioned(
                left: c.maxWidth / 2 - 40,
                top: c.maxHeight * 0.46 - 40,
                child: Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: Plataforma.oro.withValues(alpha: 0.45)),
                    color: Plataforma.coral.withValues(alpha: 0.14),
                    boxShadow: [BoxShadow(color: Plataforma.coral.withValues(alpha: 0.5), blurRadius: 40, spreadRadius: -6)],
                  ),
                  child: const Icon(Icons.cloud_upload_outlined, size: 34, color: Plataforma.oro),
                ),
              ),
              Positioned(left: c.maxWidth * 0.10, top: c.maxHeight * 0.12, child: baldosa(icono: Icons.smartphone, texto: 'App', desfase: 0)),
              Positioned(right: c.maxWidth * 0.09, top: c.maxHeight * 0.22, child: baldosa(icono: Icons.point_of_sale_outlined, texto: 'Caja', desfase: 2)),
              Positioned(left: c.maxWidth * 0.18, top: c.maxHeight * 0.60, child: baldosa(icono: Icons.web_outlined, texto: 'Web', desfase: 4)),
              Positioned(
                left: 0,
                right: 0,
                bottom: c.maxHeight * 0.09,
                child: Center(
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      Opacity(
                        opacity: sin,
                        child: Transform.translate(
                          offset: Offset(0, 6 * (1 - sin)),
                          child: const _EstadoSync(texto: 'Sin internet · 3 ventas guardadas', punto: Color(0xFFF2B84B)),
                        ),
                      ),
                      Opacity(
                        opacity: 1 - sin,
                        child: Transform.translate(
                          offset: Offset(0, -6 * sin),
                          child: const _EstadoSync(texto: 'Sincronizado', punto: Color(0xFF5FD39A), brillo: true),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _EstadoSync extends StatelessWidget {
  const _EstadoSync({required this.texto, required this.punto, this.brillo = false});

  final String texto;
  final Color punto;
  final bool brillo;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
        color: const Color(0xD90B111D),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: punto,
              shape: BoxShape.circle,
              boxShadow: brillo ? [BoxShadow(color: punto, blurRadius: 10)] : null,
            ),
          ),
          const SizedBox(width: 8),
          Text(texto, style: GoogleFonts.inter(color: Colors.white, fontSize: 11.8, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
