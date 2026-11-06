import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_client.dart';
import '../live/live_admin_screen.dart';
import '../live/live_api.dart';

const _noche = Color(0xFF121A2C);
const _gris = Color(0xFF5F6779);
const _rojo = Color(0xFFE5292F);
const _borde = Color(0xFFEDE8E2);

String _hora(DateTime f) {
  String dos(int n) => n.toString().padLeft(2, '0');
  return '${dos(f.day)}/${dos(f.month)}/${f.year} ${dos(f.hour)}:${dos(f.minute)}';
}

/// CU22 del SuperAdministrador: lives en curso de todas las tiendas (verlos y
/// moderarlos, o cortarlos si incumplen los terminos) y las grabaciones.
class SuperLive extends ConsumerStatefulWidget {
  const SuperLive({super.key});

  @override
  ConsumerState<SuperLive> createState() => _SuperLiveState();
}

class _SuperLiveState extends ConsumerState<SuperLive> {
  List<LiveResumen> _enVivo = [];
  List<LiveResumen> _historial = [];
  bool _cargando = true;
  String? _error;

  LiveApi get _api => ref.read(liveApiProvider);

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _error = null);
    try {
      final vivos = await _api.enVivo();
      final historial = await _api.historial();
      if (!mounted) return;
      setState(() {
        _enVivo = vivos;
        _historial = historial.where((l) => l.estado != 'en_vivo').toList();
      });
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _cortar(LiveResumen l) async {
    final motivo = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cortar el live'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('«${l.titulo}» de ${l.tienda}. Se cierra para todos y queda grabado; la tienda recibe el motivo.'),
          const SizedBox(height: 12),
          TextField(
            controller: motivo,
            maxLength: 500,
            decoration: const InputDecoration(labelText: 'Motivo (términos y condiciones incumplidos)'),
          ),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Cortar live', style: TextStyle(color: _rojo))),
        ],
      ),
    );
    if (ok != true) return;
    if (motivo.text.trim().length < 5) {
      setState(() => _error = 'Escribe el motivo del corte (la tienda lo recibe).');
      return;
    }
    try {
      await _api.cortar(l.id, motivo.text.trim());
      _cargar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) return const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator()));
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (_error != null)
        Container(
          padding: const EdgeInsets.all(12),
          margin: const EdgeInsets.only(bottom: 12),
          color: const Color(0xFFFDECEA),
          child: Text(_error!, style: const TextStyle(color: Color(0xFFB3261E))),
        ),
      _Seccion(
        titulo: 'En vivo ahora (${_enVivo.length})',
        hijos: [
          if (_enVivo.isEmpty) Text('Ninguna tienda está en vivo ahora.', style: GoogleFonts.inter(color: _gris)),
          for (final l in _enVivo)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 12),
              decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _borde))),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(l.tienda, style: GoogleFonts.inter(fontWeight: FontWeight.w800, color: _noche)),
                Text(l.titulo, style: GoogleFonts.inter(color: _noche)),
                Text('Desde ${_hora(l.inicio)} · viendo ${l.espectadores} · ${l.comentarios} comentarios',
                    style: GoogleFonts.inter(fontSize: 12, color: _gris)),
                const SizedBox(height: 8),
                Row(children: [
                  OutlinedButton(
                    onPressed: () async {
                      await context.push('/live/${l.id}');
                      _cargar();
                    },
                    child: const Text('VER Y MODERAR'),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: _rojo),
                    onPressed: () => _cortar(l),
                    child: const Text('CORTAR'),
                  ),
                ]),
              ]),
            ),
        ],
      ),
      const SizedBox(height: 20),
      _Seccion(
        titulo: 'Lives anteriores y grabaciones',
        hijos: [
          if (_historial.isEmpty) Text('Todavía no hay lives anteriores.', style: GoogleFonts.inter(color: _gris)),
          for (final l in _historial)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('${l.tienda} · ${l.titulo}', style: GoogleFonts.inter(fontWeight: FontWeight.w700, fontSize: 14)),
              subtitle: Text([
                _hora(l.inicio),
                l.estado == 'cortado' ? 'Cortado: ${l.motivoCorte ?? ''}' : '${l.espectadoresMax} espectadores máx. · ${l.comentarios} comentarios',
              ].join('\n')),
              isThreeLine: true,
              trailing: l.grabacion == 'lista'
                  ? IconButton(
                      tooltip: 'Ver grabación con comentarios',
                      icon: const Icon(Icons.play_circle_fill, color: _noche),
                      onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => GrabacionLiveScreen(live: l))),
                    )
                  : null,
            ),
        ],
      ),
    ]);
  }
}

class _Seccion extends StatelessWidget {
  const _Seccion({required this.titulo, required this.hijos});
  final String titulo;
  final List<Widget> hijos;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: Colors.white, border: Border.all(color: _borde)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(titulo, style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w800, color: _noche)),
          const SizedBox(height: 8),
          ...hijos,
        ]),
      );
}
