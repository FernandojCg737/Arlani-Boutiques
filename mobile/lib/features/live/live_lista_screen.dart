import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_config.dart';
import '../../widgets/whatsapp_float_button.dart';
import '../portada/encabezado_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../portada/secciones_cierre.dart';
import '../storefront/catalogo_provider.dart';
import 'live_api.dart';

const _rojo = Color(0xFFE5292F);
const _tinta = Color(0xFF121A2C);
const _gris = Color(0xFF5F6779);

/// CU22: lives en curso de todas las boutiques (boton LIVE del encabezado).
/// Igual que `/live` de la web en celular: encabezado de Arlani, "Arlani Live"
/// en rojo, el titulo, la grilla de lives y el pie de la plataforma.
class LiveListaScreen extends ConsumerStatefulWidget {
  const LiveListaScreen({super.key});

  @override
  ConsumerState<LiveListaScreen> createState() => _LiveListaScreenState();
}

class _LiveListaScreenState extends ConsumerState<LiveListaScreen> {
  Timer? _timer;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _revisar();
    _timer = Timer.periodic(const Duration(seconds: 20), (_) => _revisar());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _revisar() async {
    await ref.read(enVivoProvider.notifier).revisar();
    if (mounted) setState(() => _cargando = false);
  }

  @override
  Widget build(BuildContext context) {
    final lives = ref.watch(enVivoProvider);
    final arriba = MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto;
    void irA(SeccionPortada s) => context.go(s == SeccionPortada.inicio ? '/' : '/?seccion=${s.name}');

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: Colors.white,
        body: Stack(
          children: [
            RefreshIndicator(
              edgeOffset: arriba,
              onRefresh: _revisar,
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      padding: EdgeInsets.fromLTRB(20, arriba + 36, 20, 72),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // `.volver-link` de la web: a la pagina anterior o al inicio.
                          InkWell(
                            onTap: () => context.canPop() ? context.pop() : context.go('/'),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 6),
                              child: Row(mainAxisSize: MainAxisSize.min, children: [
                                const Icon(Icons.arrow_back, size: 16, color: _tinta),
                                const SizedBox(width: 6),
                                Text('VOLVER',
                                    style: GoogleFonts.inter(
                                        fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: _tinta)),
                              ]),
                            ),
                          ),
                          const SizedBox(height: 16),
                          Text('ARLANI LIVE',
                              style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w800, letterSpacing: 1.4, color: _rojo)),
                          const SizedBox(height: 6),
                          Text('Compra en vivo',
                              style: GoogleFonts.inter(fontSize: 30, fontWeight: FontWeight.w800, height: 1.15, color: _tinta)),
                          const SizedBox(height: 8),
                          Text(
                            'Las boutiques muestran sus prendas en directo: mira, pregunta en los comentarios y agrégalas a tu '
                            'carrito sin salir del live.',
                            style: GoogleFonts.inter(fontSize: 15.5, height: 1.55, color: _gris),
                          ),
                          const SizedBox(height: 28),
                          if (_cargando)
                            const Padding(padding: EdgeInsets.all(30), child: Center(child: CircularProgressIndicator()))
                          else if (lives.isEmpty)
                            Text(
                              'Ninguna boutique está en vivo ahora. Te avisaremos en tus notificaciones cuando alguna empiece.',
                              style: GoogleFonts.inter(fontSize: 15, height: 1.5, color: _gris),
                            )
                          else
                            GridView.count(
                              crossAxisCount: 2,
                              shrinkWrap: true,
                              physics: const NeverScrollableScrollPhysics(),
                              mainAxisSpacing: 16,
                              crossAxisSpacing: 16,
                              childAspectRatio: 0.66,
                              children: [for (final l in lives) _Tarjeta(live: l)],
                            ),
                        ],
                      ),
                    ),
                    PiePlataforma(onIrA: irA),
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
                onIrA: irA,
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

class _Tarjeta extends StatelessWidget {
  const _Tarjeta({required this.live});
  final LiveResumen live;

  @override
  Widget build(BuildContext context) {
    final desde = '${live.inicio.hour.toString().padLeft(2, '0')}:${live.inicio.minute.toString().padLeft(2, '0')}';
    return Material(
      color: Colors.white,
      elevation: 1,
      shadowColor: const Color(0x2212182C),
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/live/${live.id}'),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Expanded(
            child: Container(
              color: colorMarca(live.color),
              child: Stack(children: [
                Center(
                  child: live.logo != null
                      ? Padding(
                          padding: const EdgeInsets.all(28),
                          child: CachedNetworkImage(imageUrl: resolveImageUrl(live.logo!), fit: BoxFit.contain),
                        )
                      : Text(live.tienda.characters.first,
                          style: const TextStyle(color: Colors.white, fontSize: 48, fontWeight: FontWeight.w800)),
                ),
                Positioned(
                  top: 8,
                  left: 8,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(color: _rojo, borderRadius: BorderRadius.circular(4)),
                    child: const Text('EN VIVO', style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800)),
                  ),
                ),
                Positioned(
                  top: 8,
                  right: 8,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(color: Colors.black45, borderRadius: BorderRadius.circular(4)),
                    child: Text('👁 ${live.espectadores}', style: const TextStyle(color: Colors.white, fontSize: 11)),
                  ),
                ),
              ]),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(10),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(live.titulo,
                  maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700, color: _tinta)),
              const SizedBox(height: 2),
              Text('${live.tienda} · desde las $desde',
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: _gris)),
            ]),
          ),
        ]),
      ),
    );
  }
}
