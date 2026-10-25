import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'estilo_plataforma.dart';

/// "Hecha para boutiques como la tuya" (`por-que-arlani`): los tres tipos de
/// boutique, cada uno con su escena animada (la tienda que se arma sola, el
/// panel de sucursales y la caja que sincroniza). En la web la escena queda
/// fija y cambia con el scroll; en el celular cada paso lleva la suya arriba,
/// y se vuelve a animar cada vez que entra en pantalla.
class PorQueArlani extends StatelessWidget {
  const PorQueArlani({super.key});

  static const _pasos = [
    (
      'Para boutiques que recién empiezan',
      'Abrí tu tienda online en una tarde.',
      'Subí tus prendas con fotos, tallas y colores, elegí los colores de tu marca y listo: tus clientes ya pueden comprar, reservar y probarse la ropa con realidad aumentada.',
    ),
    (
      'Para cadenas con varias sucursales',
      'Cada sucursal, en un solo panel.',
      'Stock por sucursal y por talla, ventas del día y empleados con permisos según su cargo. Comparás tus sucursales sin pedirle planillas a nadie.',
    ),
    (
      'Para tiendas con mala señal',
      'Si se corta internet, la caja sigue.',
      'Cada venta se guarda en el dispositivo y se sincroniza sola cuando vuelve la conexión. Sin ventas perdidas y sin ventas repetidas.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final escenas = <Widget Function(double)>[
      (t) => _EscenaTienda(t: t),
      (t) => _EscenaPanel(t: t),
      (t) => _EscenaCaja(t: t),
    ];

    return Container(
      color: Plataforma.marfil,
      padding: const EdgeInsets.fromLTRB(Plataforma.margen, 72, Plataforma.margen, 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('POR QUÉ ARLANI', style: antetituloPlataforma(Plataforma.coralOscuro)),
          const SizedBox(height: 14),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: Text('HECHA PARA BOUTIQUES COMO LA TUYA.', style: tituloPlataforma(size: 35.2, color: Plataforma.noche)),
          ),
          for (var i = 0; i < _pasos.length; i++) ...[
            const SizedBox(height: 32),
            SizedBox(height: 330, child: _Escena(construir: escenas[i])),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 32),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: Plataforma.coral.withValues(alpha: 0.14),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(_pasos[i].$1,
                        style: GoogleFonts.inter(color: Plataforma.coralOscuro, fontSize: 12.5, fontWeight: FontWeight.w700)),
                  ),
                  const SizedBox(height: 12),
                  Text(_pasos[i].$2, style: bricolage(size: 27.2, color: Plataforma.noche, height: 1.08)),
                  const SizedBox(height: 16),
                  Text(_pasos[i].$3, style: GoogleFonts.inter(color: Plataforma.gris, fontSize: 16.3, height: 1.6)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Reproduce la animacion de la escena (3 s) cada vez que entra en pantalla.
class _Escena extends StatefulWidget {
  const _Escena({required this.construir});

  final Widget Function(double t) construir;

  @override
  State<_Escena> createState() => _EscenaState();
}

class _EscenaState extends State<_Escena> with SingleTickerProviderStateMixin {
  late final AnimationController _reloj = AnimationController(vsync: this, duration: const Duration(seconds: 3));
  final _clave = UniqueKey();
  bool _visible = false;

  @override
  void dispose() {
    _reloj.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return VisibilityDetector(
      key: _clave,
      onVisibilityChanged: (info) {
        if (!mounted) return;
        final ahora = info.visibleFraction > 0.5;
        if (ahora && !_visible) _reloj.forward(from: 0);
        _visible = ahora;
      },
      child: AnimatedBuilder(
        animation: _reloj,
        builder: (context, _) => Center(child: widget.construir(_reloj.value * 3000)),
      ),
    );
  }
}

const _salida = Cubic(0.16, 1, 0.3, 1);

/// Progreso 0..1 de una animacion que empieza a `desde` ms y dura `dura` ms.
double _progreso(double ms, double desde, double dura) => _salida.transform(((ms - desde) / dura).clamp(0.0, 1.0));

/// `@keyframes aparece`: entra desde abajo y se hace visible.
Widget _aparece(double p, Widget hijo, {double desde = 14}) =>
    Opacity(opacity: p, child: Transform.translate(offset: Offset(0, desde * (1 - p)), child: hijo));

BoxDecoration _tarjeta({Color color = Colors.white}) => BoxDecoration(
      color: color,
      borderRadius: BorderRadius.circular(16),
      boxShadow: const [
        BoxShadow(color: Color(0x14121A2C), blurRadius: 2, offset: Offset(0, 1)),
        BoxShadow(color: Color(0x40121A2C), blurRadius: 60, spreadRadius: -20, offset: Offset(0, 30)),
      ],
    );

String _miles(int n) {
  final s = n.toString();
  final b = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write('.');
    b.write(s[i]);
  }
  return b.toString();
}

// ----------------------------------------------------- 1. la tienda se arma

class _EscenaTienda extends StatelessWidget {
  const _EscenaTienda({required this.t});

  final double t;

  static const _productos = [
    ('Polera negra', 120, 'assets/portada/producto-1.jpg'),
    ('Polera blanca', 110, 'assets/portada/producto-2.jpg'),
    ('Chaqueta de cuero', 450, 'assets/portada/producto-4.jpg'),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          constraints: const BoxConstraints(maxWidth: 460),
          clipBehavior: Clip.antiAlias,
          decoration: _tarjeta(),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                color: const Color(0xFFEEF0F4),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                child: Row(
                  children: [
                    for (var i = 0; i < 3; i++)
                      Container(
                        width: 9,
                        height: 9,
                        margin: const EdgeInsets.only(right: 6),
                        decoration: const BoxDecoration(color: Color(0xFFCFD3DC), shape: BoxShape.circle),
                      ),
                    const SizedBox(width: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(999)),
                      child: Text('tuboutique.arlani.bo', style: GoogleFonts.inter(fontSize: 10.9, color: Plataforma.gris)),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        CustomPaint(
                          painter: _BordePunteado(),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                            child: Text('Tu logo',
                                style: GoogleFonts.inter(fontSize: 11.2, fontWeight: FontWeight.w700, color: Plataforma.coralOscuro)),
                          ),
                        ),
                        const Spacer(),
                        for (var i = 0; i < 3; i++)
                          Container(
                            width: 34,
                            height: 6,
                            margin: const EdgeInsets.only(left: 8),
                            decoration: BoxDecoration(color: const Color(0xFFE3E6EC), borderRadius: BorderRadius.circular(3)),
                          ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        for (var i = 0; i < _productos.length; i++) ...[
                          if (i > 0) const SizedBox(width: 10),
                          Expanded(
                            child: _aparece(
                              _progreso(t, 250 + i * 160.0, 600),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  ClipRRect(
                                    borderRadius: BorderRadius.circular(6),
                                    child: AspectRatio(
                                      aspectRatio: 1,
                                      child: Image.asset(_productos[i].$3, fit: BoxFit.cover),
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(_productos[i].$1,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w700, color: Plataforma.noche)),
                                  Text('${_productos[i].$2} Bs', style: GoogleFonts.inter(fontSize: 11.2, color: Plataforma.gris)),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        _aparece(
          _progreso(t, 900, 600),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(color: Plataforma.noche, borderRadius: BorderRadius.circular(999)),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.check, size: 16, color: Colors.white),
                const SizedBox(width: 8),
                Text('Tu tienda ya está publicada',
                    style: GoogleFonts.inter(color: Colors.white, fontSize: 13.1, fontWeight: FontWeight.w600)),
              ],
            ),
          ),
          desde: 10,
        ),
      ],
    );
  }
}

/// Borde punteado coral del "Tu logo" (`border: 1.5px dashed`).
class _BordePunteado extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final pincel = Paint()
      ..color = Plataforma.coral
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    final camino = Path()..addRRect(RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(6)));
    for (final metrica in camino.computeMetrics()) {
      for (double d = 0; d < metrica.length; d += 7) {
        canvas.drawPath(metrica.extractPath(d, d + 4), pincel);
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ------------------------------------------------ 2. todas las sucursales

class _EscenaPanel extends StatelessWidget {
  const _EscenaPanel({required this.t});

  final double t;

  static const _sucursales = [('Equipetrol', 5240, 1.0), ('Las Palmas', 4180, 0.8), ('Norte', 3060, 0.58)];

  @override
  Widget build(BuildContext context) {
    final total = _sucursales.fold<int>(0, (suma, s) => suma + s.$2);
    return Container(
      constraints: const BoxConstraints(maxWidth: 460),
      padding: const EdgeInsets.fromLTRB(24, 22, 24, 26),
      decoration: _tarjeta(color: Plataforma.noche),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Ventas de hoy · Todas las sucursales',
                    style: GoogleFonts.inter(fontSize: 12.5, color: Colors.white.withValues(alpha: 0.6))),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.2)),
                ),
                child: Text('Ejemplo', style: GoogleFonts.inter(fontSize: 10.6, color: Colors.white.withValues(alpha: 0.6))),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text('Bs ${_miles(total)}', style: bricolage(size: 38.4).copyWith(letterSpacing: -1.1)),
          const SizedBox(height: 20),
          for (var i = 0; i < _sucursales.length; i++) ...[
            if (i > 0) const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: Text('Sucursal ${_sucursales[i].$1}',
                      style: GoogleFonts.inter(fontSize: 13.1, color: Colors.white.withValues(alpha: 0.75))),
                ),
                Text('Bs ${_miles(_sucursales[i].$2)}',
                    style: GoogleFonts.inter(fontSize: 13.1, color: Colors.white, fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 7),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: Container(
                height: 8,
                color: Colors.white.withValues(alpha: 0.08),
                alignment: Alignment.centerLeft,
                child: FractionallySizedBox(
                  widthFactor: _sucursales[i].$3 * _progreso(t, 200 + i * 150.0, 900),
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(4),
                      gradient: const LinearGradient(
                        colors: [Plataforma.coralOscuro, Plataforma.coral, Plataforma.oro],
                        stops: [0, 0.6, 1],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

// ------------------------------------------------- 3. la caja sin internet

class _EscenaCaja extends StatelessWidget {
  const _EscenaCaja({required this.t});

  final double t;

  static const _ventas = [(1024, 'Camisa Oxford', 165), (1025, 'Chompa básica', 224), (1026, 'Gorra clásica', 96)];

  @override
  Widget build(BuildContext context) {
    final conectado = _progreso(t, 1100, 400);
    return Container(
      constraints: const BoxConstraints(maxWidth: 460),
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
      decoration: _tarjeta(),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: _Cruce(
              p: conectado,
              antes: const _Senal(texto: 'Sin conexión', fondo: Color(0xFFFDF1DC), color: Color(0xFF8A5A0B), punto: Color(0xFFE8A33B)),
              despues: const _Senal(texto: 'Conectado', fondo: Color(0xFFE3F6EC), color: Color(0xFF1D6B45), punto: Color(0xFF2FB36B)),
            ),
          ),
          const SizedBox(height: 14),
          for (var i = 0; i < _ventas.length; i++)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 12),
              decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFFEEF0F4)))),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Venta #${_ventas[i].$1}',
                            style: GoogleFonts.inter(fontSize: 13.8, fontWeight: FontWeight.w700, color: Plataforma.noche)),
                        Text('${_ventas[i].$2} · ${_ventas[i].$3} Bs', style: GoogleFonts.inter(fontSize: 12.2, color: Plataforma.gris)),
                      ],
                    ),
                  ),
                  _Cruce(
                    p: _progreso(t, 1500 + i * 450.0, 350),
                    alinear: Alignment.centerRight,
                    antes: const _Pastilla(texto: 'Guardada', fondo: Color(0xFFFDF1DC), color: Color(0xFF8A5A0B)),
                    despues: const _Pastilla(texto: 'Sincronizada', fondo: Color(0xFFE3F6EC), color: Color(0xFF1D6B45)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// Uno se va achicandose (`se-va`) y el otro aparece (`aparece-quieto`).
class _Cruce extends StatelessWidget {
  const _Cruce({required this.p, required this.antes, required this.despues, this.alinear = Alignment.centerLeft});

  final double p;
  final Widget antes;
  final Widget despues;
  final Alignment alinear;

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: alinear,
      children: [
        Opacity(opacity: 1 - p, child: Transform.scale(scale: 1 - 0.1 * p, child: antes)),
        Opacity(opacity: p, child: Transform.scale(scale: 0.9 + 0.1 * p, child: despues)),
      ],
    );
  }
}

class _Senal extends StatelessWidget {
  const _Senal({required this.texto, required this.fondo, required this.color, required this.punto});

  final String texto;
  final Color fondo;
  final Color color;
  final Color punto;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(color: fondo, borderRadius: BorderRadius.circular(999)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 8, height: 8, decoration: BoxDecoration(color: punto, shape: BoxShape.circle)),
          const SizedBox(width: 7),
          Text(texto, style: GoogleFonts.inter(fontSize: 12.2, fontWeight: FontWeight.w700, color: color)),
        ],
      ),
    );
  }
}

class _Pastilla extends StatelessWidget {
  const _Pastilla({required this.texto, required this.fondo, required this.color});

  final String texto;
  final Color fondo;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: fondo, borderRadius: BorderRadius.circular(999)),
      child: Text(texto, style: GoogleFonts.inter(fontSize: 11.2, fontWeight: FontWeight.w700, color: color)),
    );
  }
}
