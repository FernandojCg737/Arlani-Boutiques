import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:livekit_client/livekit_client.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import '../auth/auth_provider.dart';
import '../storefront/cart_provider.dart';
import 'live_api.dart';

const _rojo = Color(0xFFE5292F);
const _noche = Color(0xFF0B111D);

/// CU22: la sala de un live (`live-sala` de la web). Quien lo inicio transmite
/// con su camara; el resto del personal con permiso y el SuperAdministrador
/// moderan (ven el video, ocultan comentarios, bloquean); los clientes miran,
/// comentan, reaccionan y agregan la prenda fijada al carrito.
class LiveSalaScreen extends ConsumerStatefulWidget {
  const LiveSalaScreen({super.key, required this.liveId});

  final int liveId;

  @override
  ConsumerState<LiveSalaScreen> createState() => _LiveSalaScreenState();
}

class _Reaccion {
  _Reaccion(this.id, this.emoji, this.izquierda);
  final int id;
  final String emoji;
  final double izquierda;
}

class _LiveSalaScreenState extends ConsumerState<LiveSalaScreen> {
  Room? _room;
  EventsListener<RoomEvent>? _escucha;
  SalaLive? _sala;
  List<ComentarioLive> _comentarios = [];
  List<ProductoLive> _productos = [];
  List<EspectadorLive> _espectadores = [];
  VideoTrack? _video;
  bool _cargando = true;
  bool _silenciado = false;
  bool _mic = true;
  bool _cam = true;
  bool _frontal = true;
  bool _enviando = false;
  bool _agregando = false;
  bool _terminando = false;
  int _conectados = 0;
  String? _fin;
  String? _error;
  String _variante = '';
  String? _avisoCarrito;
  final List<_Reaccion> _reacciones = [];
  int _siguiente = 0;
  final _texto = TextEditingController();
  final _scroll = ScrollController();

  LiveApi get _api => ref.read(liveApiProvider);
  bool get _vendedor => _sala?.vendedor ?? false;
  bool get _modera => _sala?.moderador ?? false;
  ProductoLive? get _fijado => _productos.where((p) => p.fijado).firstOrNull;

  @override
  void initState() {
    super.initState();
    _entrar();
  }

  @override
  void dispose() {
    _escucha?.dispose();
    _room?.disconnect();
    _room?.dispose();
    _texto.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    try {
      final sala = await _api.sala(widget.liveId);
      if (!mounted) return;
      setState(() {
        _sala = sala;
        _comentarios = sala.comentarios;
        _productos = sala.productos;
        _espectadores = sala.espectadores;
        _silenciado = sala.silenciado;
        _cargando = false;
      });
      if (sala.vendedor) {
        final permisos = await [Permission.camera, Permission.microphone].request();
        if (permisos.values.any((p) => !p.isGranted)) {
          setState(() => _error = 'Para transmitir, permite el uso de la cámara y el micrófono.');
          return;
        }
      }
      await _conectar(sala);
    } catch (e) {
      if (mounted) {
        setState(() {
          _cargando = false;
          _error = extractErrorMessage(e);
        });
      }
    }
  }

  Future<void> _conectar(SalaLive sala) async {
    final room = Room(roomOptions: const RoomOptions(adaptiveStream: true, dynacast: true));
    _room = room;
    _escucha = room.createListener()
      ..on<TrackSubscribedEvent>((e) {
        if (e.track is VideoTrack && mounted) setState(() => _video = e.track as VideoTrack);
      })
      ..on<TrackUnsubscribedEvent>((e) {
        if (e.track == _video && mounted) setState(() => _video = null);
      })
      ..on<DataReceivedEvent>((e) {
        if (e.topic == 'live') _recibir(jsonDecode(utf8.decode(e.data)) as Map<String, dynamic>);
      })
      ..on<ParticipantConnectedEvent>((_) => _actualizarConectados())
      ..on<ParticipantDisconnectedEvent>((_) => _actualizarConectados())
      ..on<RoomDisconnectedEvent>((e) {
        if (!mounted || _fin != null) return;
        if (e.reason == DisconnectReason.participantRemoved) {
          setState(() => _fin = 'La tienda te sacó de este live.');
        } else if (e.reason == DisconnectReason.roomDeleted) {
          setState(() => _fin = 'El live terminó.');
        }
      });

    await room.connect(sala.url, sala.token);
    _actualizarConectados();
    if (sala.vendedor) {
      await room.localParticipant?.setCameraEnabled(true);
      await room.localParticipant?.setMicrophoneEnabled(true);
      final propia = room.localParticipant?.videoTrackPublications.firstOrNull?.track;
      if (mounted) setState(() => _video = propia);
      // Ya se esta transmitiendo: empieza la grabacion.
      unawaited(_api.grabar(widget.liveId).catchError((_) {}));
    } else {
      for (final p in room.remoteParticipants.values) {
        final pista = p.videoTrackPublications.firstOrNull?.track;
        if (pista != null && mounted) setState(() => _video = pista);
      }
    }
    _bajar();
  }

  String _rolDe(Participant p) {
    try {
      return (jsonDecode(p.metadata ?? '{}') as Map)['rol']?.toString() ?? '';
    } catch (_) {
      return '';
    }
  }

  void _actualizarConectados() {
    final room = _room;
    if (room == null || !mounted) return;
    setState(() => _conectados = room.remoteParticipants.values.where((p) => _rolDe(p) == 'espectador').length);
    if (_modera) _api.espectadores(widget.liveId).then((e) => mounted ? setState(() => _espectadores = e) : null, onError: (_) {});
  }

  void _recibir(Map<String, dynamic> m) {
    if (!mounted) return;
    switch (m['tipo']) {
      case 'comentario':
        final c = ComentarioLive(m['comentario'] as Map<String, dynamic>);
        if (_comentarios.any((x) => x.id == c.id)) return;
        setState(() => _comentarios = [..._comentarios.length > 199 ? _comentarios.skip(1) : _comentarios, c]);
        _bajar();
      case 'ocultar':
        final id = m['id'] as int;
        setState(() => _comentarios = _modera
            ? [for (final c in _comentarios) c.id == id ? c.ocultado() : c]
            : _comentarios.where((c) => c.id != id).toList());
      case 'productos':
        setState(() {
          _productos = [for (final p in m['productos'] as List) ProductoLive(p as Map<String, dynamic>)];
          _variante = '';
          _avisoCarrito = null;
        });
      case 'reaccion':
        _flotar(m['emoji'].toString());
      case 'bloqueo':
        if (m['usuario_id'] == ref.read(authProvider).usuario?.id) setState(() => _silenciado = m['bloqueo'] != null);
        if (_modera) _actualizarConectados();
      case 'fin':
        setState(() => _fin = (m['motivo'] as String?) ?? 'El live terminó.');
        _room?.disconnect();
    }
  }

  void _bajar() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
    });
  }

  void _flotar(String emoji) {
    final r = _Reaccion(++_siguiente, emoji, 0.55 + Random().nextDouble() * 0.35);
    setState(() => _reacciones.add(r));
    Future.delayed(const Duration(milliseconds: 2600), () {
      if (mounted) setState(() => _reacciones.removeWhere((x) => x.id == r.id));
    });
  }

  void _aviso(String texto) {
    setState(() => _error = texto);
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted && _error == texto) setState(() => _error = null);
    });
  }

  // ---------------------------------------------------------------- espectador

  Future<void> _comentar() async {
    final texto = _texto.text.trim();
    if (texto.isEmpty || _enviando) return;
    setState(() => _enviando = true);
    try {
      final c = await _api.comentar(widget.liveId, texto);
      _texto.clear();
      if (!_comentarios.any((x) => x.id == c.id)) setState(() => _comentarios = [..._comentarios, c]);
      _bajar();
    } catch (e) {
      _aviso(extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  void _reaccionar(String emoji) {
    HapticFeedback.lightImpact();
    _flotar(emoji);
    _api.reaccionar(widget.liveId, emoji).catchError((_) {});
  }

  Future<void> _agregarAlCarrito(ProductoLive p) async {
    final v = p.variantes.where((x) => x.clave == _variante).firstOrNull;
    if (v == null) {
      setState(() => _avisoCarrito = 'Elige talla y color.');
      return;
    }
    setState(() {
      _agregando = true;
      _avisoCarrito = null;
    });
    try {
      await ref.read(cartProvider.notifier).agregar(
            productoId: p.id,
            tallaId: v.tallaId,
            colorId: v.colorId,
            sucursalId: v.sucursalId,
            cantidad: 1,
          );
      setState(() => _avisoCarrito = '¡Agregado a tu carrito!');
    } catch (e) {
      setState(() => _avisoCarrito = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _agregando = false);
    }
  }

  // ------------------------------------------------------------------ vendedor

  Future<void> _alternarMic() async {
    await _room?.localParticipant?.setMicrophoneEnabled(!_mic);
    setState(() => _mic = !_mic);
  }

  Future<void> _alternarCam() async {
    await _room?.localParticipant?.setCameraEnabled(!_cam);
    setState(() {
      _cam = !_cam;
      _video = _cam ? _room?.localParticipant?.videoTrackPublications.firstOrNull?.track : null;
    });
  }

  Future<void> _girarCamara() async {
    final pista = _room?.localParticipant?.videoTrackPublications.firstOrNull?.track;
    if (pista is LocalVideoTrack) {
      await pista.setCameraPosition(_frontal ? CameraPosition.back : CameraPosition.front);
      setState(() => _frontal = !_frontal);
    }
  }

  Future<void> _terminar() async {
    final ok = await _confirmar('¿Terminar el live? Se cierra para todos y queda la grabación.', 'Terminar');
    if (!ok) return;
    setState(() => _terminando = true);
    try {
      await _api.finalizar(widget.liveId);
      setState(() => _fin = 'Terminaste el live. La grabación aparecerá en el historial en unos minutos.');
      await _room?.disconnect();
    } catch (e) {
      _aviso(extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _terminando = false);
    }
  }

  Future<bool> _confirmar(String texto, String si) async {
    final r = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text(texto),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('No')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: Text(si, style: const TextStyle(color: _rojo))),
        ],
      ),
    );
    return r ?? false;
  }

  Future<void> _bloquear(int usuarioId, String nombre, String tipo) async {
    final texto = tipo == 'expulsado'
        ? '¿Sacar a $nombre del live? No podrá volver a entrar.'
        : '¿Bloquear los comentarios de $nombre? Seguirá viendo el live, pero no podrá comentar.';
    if (!await _confirmar(texto, tipo == 'expulsado' ? 'Expulsar' : 'Bloquear')) return;
    try {
      final e = await _api.bloquear(widget.liveId, usuarioId, tipo);
      if (mounted) setState(() => _espectadores = e);
    } catch (e) {
      _aviso(extractErrorMessage(e));
    }
  }

  Future<void> _desbloquear(int usuarioId) async {
    try {
      final e = await _api.desbloquear(widget.liveId, usuarioId);
      if (mounted) setState(() => _espectadores = e);
    } catch (e) {
      _aviso(extractErrorMessage(e));
    }
  }

  Future<void> _ocultar(ComentarioLive c) async {
    try {
      await _api.ocultar(widget.liveId, c.id);
      setState(() => _comentarios = [for (final x in _comentarios) x.id == c.id ? x.ocultado() : x]);
    } catch (e) {
      _aviso(extractErrorMessage(e));
    }
  }

  Future<void> _fijar(ProductoLive? p) async {
    try {
      final productos = await _api.fijar(widget.liveId, p?.id);
      if (mounted) setState(() => _productos = productos);
    } catch (e) {
      _aviso(extractErrorMessage(e));
    }
  }

  void _abrirModeracion() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, refrescar) => _PanelModeracion(
          comentarios: _comentarios,
          espectadores: _espectadores,
          productos: _vendedor ? _productos : null,
          onOcultar: (c) async {
            await _ocultar(c);
            refrescar(() {});
          },
          onBloquear: (id, nombre, tipo) async {
            await _bloquear(id, nombre, tipo);
            refrescar(() {});
          },
          onDesbloquear: (id) async {
            await _desbloquear(id);
            refrescar(() {});
          },
          onFijar: (p) async {
            await _fijar(p);
            refrescar(() {});
          },
          bloqueoDe: (id) => _espectadores.where((e) => e.usuarioId == id).firstOrNull?.bloqueo,
        ),
      ),
    );
  }

  // -------------------------------------------------------------------- vista

  @override
  Widget build(BuildContext context) {
    final sala = _sala;
    final abajo = MediaQuery.paddingOf(context).bottom;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: _noche,
        resizeToAvoidBottomInset: true,
        body: _cargando
            ? const Center(child: CircularProgressIndicator(color: Colors.white))
            : sala == null
                ? _mensaje(_error ?? 'No se pudo entrar al live.', volver: true)
                : Stack(
                    children: [
                      Positioned.fill(
                        child: _video != null
                            ? VideoTrackRenderer(
                                _video!,
                                fit: VideoViewFit.cover,
                                mirrorMode: _vendedor && _frontal ? VideoViewMirrorMode.mirror : VideoViewMirrorMode.off,
                              )
                            : Center(
                                child: Text(
                                  _vendedor ? 'Encendiendo tu cámara…' : 'Esperando la transmisión…',
                                  style: const TextStyle(color: Color(0xFFCFD5E2)),
                                ),
                              ),
                      ),
                      // Degradados para que el texto se lea sobre el video.
                      const Positioned(top: 0, left: 0, right: 0, height: 140, child: _Degradado(arriba: true)),
                      const Positioned(bottom: 0, left: 0, right: 0, height: 380, child: _Degradado(arriba: false)),
                      SafeArea(child: _barraSuperior(sala)),
                      for (final r in _reacciones)
                        _ReaccionFlotante(key: ValueKey(r.id), emoji: r.emoji, izquierda: r.izquierda),
                      Positioned(left: 12, right: 12, bottom: abajo + 10, child: _parteInferior()),
                      if (_error != null)
                        Positioned(
                          top: MediaQuery.paddingOf(context).top + 110,
                          left: 16,
                          right: 16,
                          child: Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(color: const Color(0xFFB3261E), borderRadius: BorderRadius.circular(8)),
                            child: Text(_error!, style: const TextStyle(color: Colors.white, fontSize: 13)),
                          ),
                        ),
                      if (_fin != null) Positioned.fill(child: _mensaje(_fin!, volver: true)),
                    ],
                  ),
      ),
    );
  }

  Widget _mensaje(String texto, {bool volver = false}) => Container(
        color: _noche.withValues(alpha: 0.9),
        padding: const EdgeInsets.all(28),
        alignment: Alignment.center,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(texto, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white, fontSize: 16)),
          if (volver) ...[
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => context.canPop() ? context.pop() : context.go('/live'),
              child: const Text('Volver', style: TextStyle(color: Color(0xFFFFD28A), fontWeight: FontWeight.w700)),
            ),
          ],
        ]),
      );

  Widget _barraSuperior(SalaLive sala) {
    final live = sala.live;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 6, 12, 0),
      child: Column(children: [
        Row(children: [
          IconButton(
            icon: const Icon(Icons.close, color: Colors.white),
            tooltip: 'Salir',
            onPressed: () => context.canPop() ? context.pop() : context.go('/live'),
          ),
          if (live.logo != null)
            CircleAvatar(
              radius: 17,
              backgroundColor: Colors.white,
              backgroundImage: CachedNetworkImageProvider(resolveImageUrl(live.logo!)),
            ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(live.tienda, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13)),
              Text(live.titulo,
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.white70, fontSize: 12)),
            ]),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: _rojo, borderRadius: BorderRadius.circular(4)),
            child: Text('EN VIVO', style: GoogleFonts.inter(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800)),
          ),
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: Colors.black45, borderRadius: BorderRadius.circular(4)),
            child: Text('👁 $_conectados', style: const TextStyle(color: Colors.white, fontSize: 12)),
          ),
        ]),
        if (_vendedor || _modera)
          Padding(
            padding: const EdgeInsets.only(top: 6, left: 8),
            child: Wrap(spacing: 6, runSpacing: 6, children: [
              if (_vendedor) ...[
                _Pildora(_mic ? '🎙️ Silenciar' : '🔇 Micrófono', _alternarMic),
                _Pildora(_cam ? '📷 Apagar cámara' : '📷 Cámara', _alternarCam),
                _Pildora('🔄 Girar', _girarCamara),
              ],
              _Pildora('🛡️ Moderar', _abrirModeracion),
              if (_vendedor) _Pildora(_terminando ? 'Terminando…' : 'Terminar live', _terminando ? null : _terminar, rojo: true),
            ]),
          ),
      ]),
    );
  }

  Widget _parteInferior() {
    final fijado = _fijado;
    final auth = ref.watch(authProvider);
    final puedeComprar = auth.isAuthenticated && !auth.isStaff;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
      // Comentarios sobre el video (los ultimos).
      ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 170),
        child: ShaderMask(
          shaderCallback: (r) => const LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Colors.transparent, Colors.white],
            stops: [0, 0.25],
          ).createShader(r),
          blendMode: BlendMode.dstIn,
          child: ListView(
            controller: _scroll,
            shrinkWrap: true,
            padding: EdgeInsets.zero,
            children: [
              for (final c in _comentarios.where((c) => !c.oculto))
                Padding(
                  padding: const EdgeInsets.only(bottom: 5),
                  child: Text.rich(
                    TextSpan(children: [
                      TextSpan(
                        text: '${c.usuario}  ',
                        style: TextStyle(color: c.esTienda ? const Color(0xFF8FE3FF) : const Color(0xFFFFD28A), fontWeight: FontWeight.w700),
                      ),
                      TextSpan(text: c.texto),
                    ]),
                    style: const TextStyle(color: Colors.white, fontSize: 13, height: 1.35, shadows: [Shadow(blurRadius: 3)]),
                  ),
                ),
            ],
          ),
        ),
      ),
      if (fijado != null) ...[
        const SizedBox(height: 8),
        _tarjetaPrenda(fijado, puedeComprar),
      ],
      if (!_vendedor && _fin == null) ...[
        const SizedBox(height: 8),
        if (_silenciado)
          const Text('La tienda bloqueó tus comentarios en este live.', style: TextStyle(color: Colors.white70, fontSize: 12))
        else
          Row(children: [
            Expanded(
              child: TextField(
                controller: _texto,
                maxLength: 300,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _comentar(),
                style: const TextStyle(color: Color(0xFF121A2C)),
                decoration: InputDecoration(
                  counterText: '',
                  hintText: 'Escribe un comentario…',
                  isDense: true,
                  filled: true,
                  fillColor: Colors.white.withValues(alpha: 0.92),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(30), borderSide: BorderSide.none),
                ),
              ),
            ),
            const SizedBox(width: 6),
            IconButton.filled(
              style: IconButton.styleFrom(backgroundColor: _rojo),
              onPressed: _enviando ? null : _comentar,
              icon: const Icon(Icons.send, color: Colors.white, size: 20),
            ),
          ]),
        const SizedBox(height: 8),
        Row(children: [
          for (final e in emojisLive)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: InkResponse(
                onTap: () => _reaccionar(e),
                onLongPress: () => _texto.text += e,
                radius: 22,
                child: Container(
                  width: 38,
                  height: 38,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.18), shape: BoxShape.circle),
                  child: Text(e, style: const TextStyle(fontSize: 18)),
                ),
              ),
            ),
        ]),
      ],
    ]);
  }

  Widget _tarjetaPrenda(ProductoLive p, bool puedeComprar) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (p.imagen != null)
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: CachedNetworkImage(imageUrl: resolveImageUrl(p.imagen!), width: 62, height: 78, fit: BoxFit.cover),
          ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(p.nombre, style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF121A2C))),
            Text.rich(TextSpan(children: [
              TextSpan(text: 'Bs ${p.precio.toStringAsFixed(2)}'),
              if (p.precioOriginal != null && p.precioOriginal! > p.precio)
                TextSpan(
                  text: '  Bs ${p.precioOriginal!.toStringAsFixed(2)}',
                  style: const TextStyle(color: Colors.grey, decoration: TextDecoration.lineThrough),
                ),
            ])),
            if (puedeComprar) ...[
              if (p.variantes.isEmpty)
                const Text('Sin stock por ahora', style: TextStyle(color: Colors.grey, fontSize: 12))
              else ...[
                DropdownButton<String>(
                  isExpanded: true,
                  isDense: true,
                  value: _variante.isEmpty ? null : _variante,
                  hint: const Text('Elige talla y color', style: TextStyle(fontSize: 12)),
                  items: [
                    for (final v in p.variantes)
                      DropdownMenuItem(value: v.clave, child: Text(v.texto, style: const TextStyle(fontSize: 12))),
                  ],
                  onChanged: (v) => setState(() => _variante = v ?? ''),
                ),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: const Color(0xFF121A2C), shape: const RoundedRectangleBorder()),
                    onPressed: _agregando ? null : () => _agregarAlCarrito(p),
                    child: Text(_agregando ? 'Agregando…' : 'Agregar al carrito'),
                  ),
                ),
              ],
              if (_avisoCarrito != null)
                Row(children: [
                  Flexible(
                    child: Text(_avisoCarrito!,
                        style: TextStyle(fontSize: 12, color: _avisoCarrito!.startsWith('¡') ? const Color(0xFF2E7D32) : _rojo)),
                  ),
                  if (_avisoCarrito!.startsWith('¡'))
                    TextButton(onPressed: () => context.push('/carrito'), child: const Text('Ver carrito')),
                ]),
            ],
          ]),
        ),
      ]),
    );
  }
}

class _Pildora extends StatelessWidget {
  const _Pildora(this.texto, this.onTap, {this.rojo = false});
  final String texto;
  final VoidCallback? onTap;
  final bool rojo;

  @override
  Widget build(BuildContext context) => Material(
        color: rojo ? _rojo : Colors.black54,
        borderRadius: BorderRadius.circular(30),
        child: InkWell(
          borderRadius: BorderRadius.circular(30),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            child: Text(texto, style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: rojo ? FontWeight.w700 : FontWeight.w500)),
          ),
        ),
      );
}

class _Degradado extends StatelessWidget {
  const _Degradado({required this.arriba});
  final bool arriba;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: arriba ? Alignment.topCenter : Alignment.bottomCenter,
              end: arriba ? Alignment.bottomCenter : Alignment.topCenter,
              colors: [Colors.black.withValues(alpha: 0.6), Colors.transparent],
            ),
          ),
        ),
      );
}

/// Emoji que sube y se desvanece (las reacciones del live).
class _ReaccionFlotante extends StatelessWidget {
  const _ReaccionFlotante({super.key, required this.emoji, required this.izquierda});
  final String emoji;
  final double izquierda;

  @override
  Widget build(BuildContext context) {
    final alto = MediaQuery.sizeOf(context).height;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 2600),
      curve: Curves.easeOut,
      builder: (context, t, _) => Positioned(
        left: MediaQuery.sizeOf(context).width * izquierda,
        bottom: alto * 0.28 + t * 240,
        child: IgnorePointer(
          child: Opacity(
            opacity: t < 0.15 ? t / 0.15 : 1 - t,
            child: Transform.scale(scale: 0.7 + t * 0.5, child: Text(emoji, style: const TextStyle(fontSize: 28))),
          ),
        ),
      ),
    );
  }
}

/// Panel de moderacion: comentarios (ocultar, bloquear), espectadores
/// (bloquear comentarios, expulsar) y, para quien transmite, las prendas.
class _PanelModeracion extends StatelessWidget {
  const _PanelModeracion({
    required this.comentarios,
    required this.espectadores,
    required this.productos,
    required this.onOcultar,
    required this.onBloquear,
    required this.onDesbloquear,
    required this.onFijar,
    required this.bloqueoDe,
  });

  final List<ComentarioLive> comentarios;
  final List<EspectadorLive> espectadores;
  final List<ProductoLive>? productos;
  final Future<void> Function(ComentarioLive) onOcultar;
  final Future<void> Function(int, String, String) onBloquear;
  final Future<void> Function(int) onDesbloquear;
  final Future<void> Function(ProductoLive?) onFijar;
  final String? Function(int) bloqueoDe;

  @override
  Widget build(BuildContext context) {
    final pestanas = ['Comentarios (${comentarios.length})', 'Espectadores (${espectadores.length})', if (productos != null) 'Prendas'];
    String hora(DateTime f) =>
        '${f.hour.toString().padLeft(2, '0')}:${f.minute.toString().padLeft(2, '0')}:${f.second.toString().padLeft(2, '0')}';
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.7,
      child: DefaultTabController(
        length: pestanas.length,
        child: Column(children: [
          TabBar(isScrollable: true, tabs: [for (final p in pestanas) Tab(text: p)]),
          Expanded(
            child: TabBarView(children: [
              ListView(padding: const EdgeInsets.all(12), children: [
                if (comentarios.isEmpty) const Padding(padding: EdgeInsets.all(20), child: Text('Todavía no hay comentarios.')),
                for (final c in comentarios.reversed)
                  Opacity(
                    opacity: c.oculto ? 0.45 : 1,
                    child: ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text.rich(TextSpan(children: [
                        TextSpan(text: c.usuario, style: const TextStyle(fontWeight: FontWeight.w700)),
                        if (c.esTienda) const TextSpan(text: '  · Tienda', style: TextStyle(color: Color(0xFF1C5FA8), fontSize: 12)),
                        if (bloqueoDe(c.usuarioId) != null)
                          TextSpan(
                            text: bloqueoDe(c.usuarioId) == 'expulsado' ? '  · Expulsado' : '  · Bloqueado',
                            style: const TextStyle(color: _rojo, fontSize: 12),
                          ),
                      ])),
                      subtitle: Text('${c.texto}\n${hora(c.fecha)}${c.oculto ? ' · Oculto' : ''}'),
                      isThreeLine: true,
                      trailing: c.oculto || c.esTienda
                          ? null
                          : PopupMenuButton<String>(
                              onSelected: (accion) => accion == 'ocultar'
                                  ? onOcultar(c)
                                  : onBloquear(c.usuarioId, c.usuario, accion == 'expulsar' ? 'expulsado' : 'silenciado'),
                              itemBuilder: (_) => [
                                const PopupMenuItem(value: 'ocultar', child: Text('Ocultar comentario')),
                                if (bloqueoDe(c.usuarioId) == null) ...[
                                  const PopupMenuItem(value: 'bloquear', child: Text('Bloquear comentarios')),
                                  const PopupMenuItem(value: 'expulsar', child: Text('Expulsar del live')),
                                ],
                              ],
                            ),
                    ),
                  ),
              ]),
              ListView(padding: const EdgeInsets.all(12), children: [
                if (espectadores.isEmpty) const Padding(padding: EdgeInsets.all(20), child: Text('Todavía no entró nadie.')),
                for (final e in espectadores)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(e.nombre, style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text([
                      e.conectado ? 'Viendo ahora' : 'Salió',
                      '${e.comentarios} comentarios',
                      if (e.bloqueo != null) e.bloqueo == 'expulsado' ? 'Expulsado' : 'Comentarios bloqueados',
                    ].join(' · ')),
                    trailing: e.bloqueo != null
                        ? TextButton(onPressed: () => onDesbloquear(e.usuarioId), child: const Text('Desbloquear'))
                        : PopupMenuButton<String>(
                            onSelected: (accion) => onBloquear(e.usuarioId, e.nombre, accion),
                            itemBuilder: (_) => const [
                              PopupMenuItem(value: 'silenciado', child: Text('Bloquear comentarios')),
                              PopupMenuItem(value: 'expulsado', child: Text('Expulsar del live')),
                            ],
                          ),
                  ),
              ]),
              if (productos != null)
                ListView(padding: const EdgeInsets.all(12), children: [
                  if (productos!.isEmpty) const Padding(padding: EdgeInsets.all(20), child: Text('No elegiste prendas para este live.')),
                  for (final p in productos!)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      tileColor: p.fijado ? const Color(0xFFFFF8EB) : null,
                      leading: p.imagen == null
                          ? null
                          : CachedNetworkImage(imageUrl: resolveImageUrl(p.imagen!), width: 44, height: 54, fit: BoxFit.cover),
                      title: Text(p.nombre),
                      subtitle: Text('Bs ${p.precio.toStringAsFixed(2)} · ${p.variantes.length} variantes con stock'),
                      trailing: p.fijado
                          ? TextButton(onPressed: () => onFijar(null), child: const Text('Quitar'))
                          : FilledButton(onPressed: () => onFijar(p), child: const Text('Mostrar')),
                    ),
                ]),
            ]),
          ),
        ]),
      ),
    );
  }
}
