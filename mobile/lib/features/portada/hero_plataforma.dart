import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:video_player/video_player.dart';

import 'estilo_plataforma.dart';

/// Hero de la portada (`<app-hero>` de `pages/home/home.html`): video de
/// fondo, "TU BOUTIQUE PUEDE SER" + una palabra que rota en oro rosa, y los
/// dos botones inclinados abajo al centro. Mide todo el alto de la pantalla.
class HeroPlataforma extends StatefulWidget {
  const HeroPlataforma({super.key, required this.onExplorar, required this.onVerPlanes});

  final VoidCallback onExplorar;
  final VoidCallback onVerPlanes;

  static const frases = ['online', 'imparable', 'inteligente', 'multisucursal', 'tendencia'];

  @override
  State<HeroPlataforma> createState() => _HeroPlataformaState();
}

class _HeroPlataformaState extends State<HeroPlataforma> {
  late final VideoPlayerController _video;
  bool _videoListo = false;
  int _frase = 0;
  Timer? _temporizador;

  @override
  void initState() {
    super.initState();
    _video = VideoPlayerController.asset('assets/video/hero.mp4')
      ..setLooping(true)
      ..setVolume(0)
      ..initialize().then((_) {
        if (!mounted) return;
        setState(() => _videoListo = true);
        _video.play();
      });
    // Igual que INTERVALO_FRASE_MS en hero.ts.
    _temporizador = Timer.periodic(const Duration(milliseconds: 2800), (_) {
      if (mounted) setState(() => _frase = (_frase + 1) % HeroPlataforma.frases.length);
    });
  }

  @override
  void dispose() {
    _temporizador?.cancel();
    _video.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pantalla = MediaQuery.sizeOf(context);
    final alto = math.max(480.0, pantalla.height);
    // h1: clamp(30px, 9vw, 64px)
    final tamTitulo = (pantalla.width * 0.09).clamp(30.0, 64.0);

    return SizedBox(
      height: alto,
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
          if (_videoListo)
            ClipRect(
              child: FittedBox(
                fit: BoxFit.cover,
                child: SizedBox(
                  width: _video.value.size.width,
                  height: _video.value.size.height,
                  child: VideoPlayer(_video),
                ),
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
          Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.white.withValues(alpha: 0.5)),
                      color: Colors.black.withValues(alpha: 0.12),
                    ),
                    child: Text(
                      'LA PLATAFORMA PARA BOUTIQUES DE BOLIVIA',
                      style: GoogleFonts.inter(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.9),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text('TU BOUTIQUE\nPUEDE SER', style: tituloPlataforma(size: tamTitulo)),
                  _FraseRotativa(
                    texto: HeroPlataforma.frases[_frase].toUpperCase(),
                    estilo: tituloPlataforma(size: tamTitulo, color: Plataforma.oro),
                  ),
                  const SizedBox(height: 12),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 440),
                    child: Text(
                      'Vendé en línea y en mostrador, en todas tus sucursales, aunque se caiga internet.',
                      style: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.9),
                        fontSize: (pantalla.width * 0.022).clamp(13.0, 16.0),
                        height: 1.5,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          // .hero-cta: abajo al centro, ancho min(300px, 82%), separados 3px.
          Positioned(
            left: 0,
            right: 0,
            bottom: 80,
            child: Center(
              child: SizedBox(
                width: math.min(300, pantalla.width * 0.82),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _BotonInclinado(texto: 'Explorar catálogos', onTap: widget.onExplorar),
                    const SizedBox(height: 3),
                    _BotonInclinado(texto: 'Ver planes', onTap: widget.onVerPlanes, secundario: true),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// La palabra que cambia: entra desde abajo y la anterior sale hacia arriba
/// (`.hero-frase--activa` / `--saliente`, 600 ms).
class _FraseRotativa extends StatelessWidget {
  const _FraseRotativa({required this.texto, required this.estilo});

  final String texto;
  final TextStyle estilo;

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 600),
        switchInCurve: const Cubic(0.16, 1, 0.3, 1),
        switchOutCurve: const Cubic(0.16, 1, 0.3, 1),
        layoutBuilder: (actual, anteriores) => Stack(alignment: Alignment.centerLeft, children: [...anteriores, ?actual]),
        transitionBuilder: (hijo, animacion) {
          final entra = hijo.key == ValueKey(texto);
          final desde = entra ? const Offset(0, 1.05) : const Offset(0, -1.05);
          return SlideTransition(
            position: Tween(begin: desde, end: Offset.zero).animate(animacion),
            child: FadeTransition(opacity: animacion, child: hijo),
          );
        },
        child: Text(texto, key: ValueKey(texto), style: estilo, maxLines: 1, softWrap: false),
      ),
    );
  }
}

/// `.hero-cta__btn`: boton inclinado (skewX -10deg) con el texto derecho.
class _BotonInclinado extends StatelessWidget {
  const _BotonInclinado({required this.texto, required this.onTap, this.secundario = false});

  final String texto;
  final VoidCallback onTap;
  final bool secundario;

  @override
  Widget build(BuildContext context) {
    return Transform(
      alignment: Alignment.center,
      transform: Matrix4.skewX(-0.176), // tan(10deg)
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
            decoration: BoxDecoration(
              color: secundario ? null : const Color(0xCC080C0C),
              border: secundario
                  ? Border.all(color: Colors.white.withValues(alpha: 0.7))
                  : Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.25))),
              boxShadow: secundario ? null : const [BoxShadow(color: Color(0x59000000), offset: Offset(5, 5))],
            ),
            child: Transform(
              alignment: Alignment.center,
              transform: Matrix4.skewX(0.176),
              child: Text(
                texto.toUpperCase(),
                style: GoogleFonts.inter(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.72),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
