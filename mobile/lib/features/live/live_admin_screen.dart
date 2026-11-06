import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:video_player/video_player.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import 'live_api.dart';

const _rojo = Color(0xFFE5292F);
const _tinta = Color(0xFF121A2C);

String _hora(DateTime f, {bool fecha = true}) {
  String dos(int n) => n.toString().padLeft(2, '0');
  final h = '${dos(f.hour)}:${dos(f.minute)}';
  return fecha ? '${dos(f.day)}/${dos(f.month)}/${f.year} $h' : h;
}

String _minuto(int s) {
  String dos(int n) => n.toString().padLeft(2, '0');
  return s >= 3600 ? '${s ~/ 3600}:${dos(s % 3600 ~/ 60)}:${dos(s % 60)}' : '${dos(s ~/ 60)}:${dos(s % 60)}';
}

/// CU22 en el panel de la tienda (`/admin/live` de la web): iniciar un live
/// (titulo y prendas), volver al que esta en curso y ver o borrar las
/// grabaciones, con sus comentarios.
class LiveAdminScreen extends ConsumerStatefulWidget {
  const LiveAdminScreen({super.key});

  @override
  ConsumerState<LiveAdminScreen> createState() => _LiveAdminScreenState();
}

class _LiveAdminScreenState extends ConsumerState<LiveAdminScreen> {
  bool _cargando = true;
  String? _error;
  Map<String, dynamic>? _estado;
  List<Map<String, dynamic>> _productos = [];
  List<LiveResumen> _historial = [];
  final Set<int> _elegidos = {};
  final _titulo = TextEditingController();
  final _descripcion = TextEditingController();
  String _buscar = '';
  bool _iniciando = false;

  LiveApi get _api => ref.read(liveApiProvider);

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void dispose() {
    _titulo.dispose();
    _descripcion.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    setState(() => _error = null);
    try {
      final estado = await _api.estadoTienda();
      final historial = await _api.historial();
      final productos = estado['disponible'] == true && estado['actual'] == null && _productos.isEmpty
          ? await _api.productosTienda()
          : _productos;
      if (!mounted) return;
      setState(() {
        _estado = estado;
        _historial = historial.where((l) => l.estado != 'en_vivo').toList();
        _productos = productos;
      });
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _iniciar() async {
    if (_titulo.text.trim().length < 3) {
      setState(() => _error = 'Ponle un título a tu live (por ejemplo: "Nueva colección de verano").');
      return;
    }
    setState(() {
      _iniciando = true;
      _error = null;
    });
    try {
      final sala = await _api.iniciar(_titulo.text.trim(), _descripcion.text.trim(), _elegidos.toList());
      _titulo.clear();
      _descripcion.clear();
      _elegidos.clear();
      if (!mounted) return;
      await context.push('/live/${sala.live.id}');
      _cargar();
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _iniciando = false);
    }
  }

  Future<void> _borrarGrabacion(LiveResumen l) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text('¿Borrar la grabación de «${l.titulo}»? No se puede recuperar.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('No')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Borrar', style: TextStyle(color: _rojo))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _api.borrarGrabacion(l.id);
      _cargar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final estado = _estado;
    final actual = estado?['actual'] == null ? null : LiveResumen(estado!['actual'] as Map<String, dynamic>);
    final filtrados = _buscar.isEmpty
        ? _productos
        : _productos.where((p) => p['nombre'].toString().toLowerCase().contains(_buscar.toLowerCase())).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Live Commerce')),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _cargar,
              child: ListView(padding: const EdgeInsets.all(16), children: [
                if (_error != null)
                  Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(12),
                    color: const Color(0xFFFDECEA),
                    child: Text(_error!, style: const TextStyle(color: Color(0xFFB3261E))),
                  ),
                if (estado == null)
                  const SizedBox()
                else if (estado['configurado'] != true)
                  const _Aviso('El live todavía no está configurado en el servidor (faltan las credenciales de LiveKit).')
                else if (estado['disponible'] != true)
                  _Aviso('El live commerce es del plan Profesional. Tu tienda tiene el plan ${estado['plan'] ?? 'actual'}.')
                else if (actual != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('Tu tienda está EN VIVO', style: TextStyle(color: _rojo, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 4),
                        Text(actual.titulo, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                        Text('Desde las ${_hora(actual.inicio, fecha: false)} · ${actual.iniciadoPor ?? ''}'),
                        const SizedBox(height: 12),
                        FilledButton.icon(
                          style: FilledButton.styleFrom(backgroundColor: _rojo),
                          onPressed: () async {
                            await context.push('/live/${actual.id}');
                            _cargar();
                          },
                          icon: const Icon(Icons.videocam),
                          label: const Text('Entrar al live'),
                        ),
                      ]),
                    ),
                  )
                else ...[
                  const Text('Iniciar un live', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: _tinta)),
                  const SizedBox(height: 10),
                  TextField(controller: _titulo, maxLength: 120, decoration: const InputDecoration(labelText: 'Título')),
                  TextField(
                    controller: _descripcion,
                    maxLength: 500,
                    decoration: const InputDecoration(labelText: 'Descripción (opcional)'),
                  ),
                  Text('Prendas que vas a mostrar (${_elegidos.length})', style: const TextStyle(fontWeight: FontWeight.w700)),
                  TextField(
                    decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Buscar prenda…'),
                    onChanged: (v) => setState(() => _buscar = v.trim()),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    height: 280,
                    child: ListView(children: [
                      for (final p in filtrados)
                        CheckboxListTile(
                          value: _elegidos.contains(p['id']),
                          onChanged: (v) => setState(() => v == true ? _elegidos.add(p['id'] as int) : _elegidos.remove(p['id'])),
                          secondary: p['imagen'] == null
                              ? null
                              : CachedNetworkImage(imageUrl: resolveImageUrl(p['imagen'].toString()), width: 40, height: 50, fit: BoxFit.cover),
                          title: Text(p['nombre'].toString()),
                          subtitle: Text('Bs ${(p['precio'] as num).toStringAsFixed(2)} · stock ${p['stock']}'),
                        ),
                    ]),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Al iniciar, el teléfono te pedirá permiso para la cámara y el micrófono. Los clientes reciben una notificación '
                    '(y un correo los que ya compraron en tu tienda). Si sales del live y no vuelves en 5 minutos, termina solo.',
                    style: TextStyle(fontSize: 12.5, color: Colors.black54),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: _rojo, minimumSize: const Size.fromHeight(48)),
                    onPressed: _iniciando ? null : _iniciar,
                    icon: const Icon(Icons.fiber_manual_record),
                    label: Text(_iniciando ? 'Iniciando…' : 'Iniciar live'),
                  ),
                ],
                const SizedBox(height: 28),
                const Text('Lives anteriores y grabaciones', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: _tinta)),
                const SizedBox(height: 8),
                if (_historial.isEmpty) const Text('Todavía no hay lives anteriores.', style: TextStyle(color: Colors.black54)),
                for (final l in _historial)
                  Card(
                    child: ListTile(
                      title: Text(l.titulo, style: const TextStyle(fontWeight: FontWeight.w700)),
                      subtitle: Text([
                        _hora(l.inicio),
                        '${l.espectadoresMax} espectadores máx. · ${l.comentarios} comentarios',
                        l.estado == 'cortado' ? 'Cortado: ${l.motivoCorte ?? ''}' : _estadoGrabacion(l),
                      ].join('\n')),
                      isThreeLine: true,
                      trailing: Wrap(children: [
                        if (l.grabacion == 'lista')
                          IconButton(
                            tooltip: 'Ver grabación',
                            icon: const Icon(Icons.play_circle_fill, color: _tinta),
                            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => _GrabacionScreen(live: l))),
                          ),
                        if (l.grabacion == 'lista' || l.grabacion == 'fallida')
                          IconButton(
                            tooltip: 'Borrar grabación',
                            icon: const Icon(Icons.delete_outline, color: _rojo),
                            onPressed: () => _borrarGrabacion(l),
                          ),
                      ]),
                    ),
                  ),
              ]),
            ),
    );
  }

  String _estadoGrabacion(LiveResumen l) => switch (l.grabacion) {
        'lista' => 'Grabación lista',
        'grabando' || 'procesando' => 'Procesando la grabación…',
        'fallida' => 'No se pudo grabar',
        'borrada' => 'Grabación borrada',
        _ => 'Sin grabación',
      };
}

class _Aviso extends StatelessWidget {
  const _Aviso(this.texto);
  final String texto;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        color: const Color(0xFFFFF4E0),
        child: Text(texto, style: const TextStyle(color: Color(0xFF8A4F00))),
      );
}

/// La grabacion y, debajo, los comentarios del live con su minuto, fecha y
/// hora y quien los escribio (tocarlos lleva el video a ese minuto).
class _GrabacionScreen extends ConsumerStatefulWidget {
  const _GrabacionScreen({required this.live});
  final LiveResumen live;

  @override
  ConsumerState<_GrabacionScreen> createState() => _GrabacionScreenState();
}

class _GrabacionScreenState extends ConsumerState<_GrabacionScreen> {
  VideoPlayerController? _video;
  List<ComentarioLive> _comentarios = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _abrir();
  }

  @override
  void dispose() {
    _video?.dispose();
    super.dispose();
  }

  Future<void> _abrir() async {
    try {
      final api = ref.read(liveApiProvider);
      final url = await api.grabacion(widget.live.id);
      final comentarios = await api.comentariosDelLive(widget.live.id);
      final video = VideoPlayerController.networkUrl(Uri.parse(url));
      await video.initialize();
      video.addListener(() {
        if (mounted) setState(() {});
      });
      await video.play();
      if (!mounted) return;
      setState(() {
        _video = video;
        _comentarios = comentarios;
      });
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final video = _video;
    final segundo = video?.value.position.inSeconds ?? 0;
    return Scaffold(
      appBar: AppBar(title: Text(widget.live.titulo)),
      body: _error != null
          ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_error!)))
          : video == null
              ? const Center(child: CircularProgressIndicator())
              : Column(children: [
                  Container(
                    color: Colors.black,
                    constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.45),
                    child: AspectRatio(
                      aspectRatio: video.value.aspectRatio,
                      child: Stack(alignment: Alignment.bottomCenter, children: [
                        VideoPlayer(video),
                        VideoProgressIndicator(video, allowScrubbing: true),
                        Center(
                          child: IconButton(
                            iconSize: 48,
                            color: Colors.white70,
                            icon: Icon(video.value.isPlaying ? Icons.pause_circle : Icons.play_circle),
                            onPressed: () => video.value.isPlaying ? video.pause() : video.play(),
                          ),
                        ),
                      ]),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                    child: Row(children: [
                      Text('Comentarios del live (${_comentarios.length})', style: const TextStyle(fontWeight: FontWeight.w800)),
                      const Spacer(),
                      Text('${_minuto(segundo)} / ${_minuto(video.value.duration.inSeconds)}',
                          style: const TextStyle(fontSize: 12, color: Colors.black54)),
                    ]),
                  ),
                  Expanded(
                    child: _comentarios.isEmpty
                        ? const Center(child: Text('En este live nadie comentó.'))
                        : ListView(children: [
                            for (final c in _comentarios)
                              ListTile(
                                dense: true,
                                tileColor: c.segundo <= segundo ? null : const Color(0xFFFAFAFA),
                                leading: Text(_minuto(c.segundo),
                                    style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()], color: Colors.black54)),
                                title: Text.rich(TextSpan(children: [
                                  TextSpan(text: '${c.usuario}  ', style: const TextStyle(fontWeight: FontWeight.w700)),
                                  if (c.esTienda) const TextSpan(text: 'Tienda  ', style: TextStyle(color: Color(0xFF1C5FA8), fontSize: 11)),
                                  TextSpan(
                                    text: c.texto,
                                    style: TextStyle(decoration: c.oculto ? TextDecoration.lineThrough : null),
                                  ),
                                ])),
                                subtitle: Text('${_hora(c.fecha)}:${c.fecha.second.toString().padLeft(2, '0')}${c.oculto ? ' · Oculto' : ''}'),
                                onTap: () => video.seekTo(Duration(seconds: c.segundo)),
                              ),
                          ]),
                  ),
                ]),
    );
  }
}
