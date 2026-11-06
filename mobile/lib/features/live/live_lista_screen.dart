import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_config.dart';
import '../portada/plataforma_data.dart' show colorMarca;
import 'live_api.dart';

/// CU22: lives en curso de todas las boutiques (boton LIVE del encabezado).
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
    return Scaffold(
      backgroundColor: const Color(0xFFF7F4F2),
      appBar: AppBar(
        backgroundColor: const Color(0xFF121A2C),
        foregroundColor: Colors.white,
        title: Text('Compra en vivo', style: GoogleFonts.inter(fontWeight: FontWeight.w800)),
      ),
      body: RefreshIndicator(
        onRefresh: _revisar,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Las boutiques muestran sus prendas en directo: mira, pregunta en los comentarios y agrégalas a tu carrito sin salir del live.',
              style: GoogleFonts.inter(fontSize: 13.5, height: 1.5, color: const Color(0xFF5F6779)),
            ),
            const SizedBox(height: 16),
            if (_cargando)
              const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator()))
            else if (lives.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 40),
                child: Text(
                  'Ninguna boutique está en vivo ahora. Te avisaremos en tus notificaciones cuando alguna empiece.',
                  textAlign: TextAlign.center,
                  style: GoogleFonts.inter(color: const Color(0xFF5F6779)),
                ),
              )
            else
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 14,
                crossAxisSpacing: 14,
                childAspectRatio: 0.68,
                children: [for (final l in lives) _Tarjeta(live: l)],
              ),
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
                    decoration: BoxDecoration(color: const Color(0xFFE5292F), borderRadius: BorderRadius.circular(4)),
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
              Text(live.titulo, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 2),
              Text('${live.tienda} · desde las $desde',
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: Color(0xFF5F6779))),
            ]),
          ),
        ]),
      ),
    );
  }
}
