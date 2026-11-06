import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_provider.dart';

/// CU22 Live commerce (`services/live.ts` de la web): tipos y llamadas a
/// `/live`. El video va por LiveKit; esto guarda y reparte lo demas.

DateTime _fecha(dynamic v) {
  final s = v.toString();
  // El backend manda UTC sin zona.
  return DateTime.parse(RegExp(r'([zZ]|[+-]\d\d:?\d\d)$').hasMatch(s) ? s : '${s}Z').toLocal();
}

class LiveResumen {
  LiveResumen(this.j);
  final Map<String, dynamic> j;

  int get id => j['id'] as int;
  int get empresaId => j['empresa_id'] as int;
  String get tienda => j['tienda'].toString();
  String? get logo => j['logo_url'] as String?;
  String? get color => j['color_marca'] as String?;
  String get titulo => j['titulo'].toString();
  String get estado => j['estado'].toString();
  DateTime get inicio => _fecha(j['inicio']);
  DateTime? get fin => j['fin'] == null ? null : _fecha(j['fin']);
  int get espectadores => (j['espectadores'] as num?)?.toInt() ?? 0;
  int get espectadoresMax => (j['espectadores_max'] as num?)?.toInt() ?? 0;
  int get comentarios => (j['comentarios'] as num?)?.toInt() ?? 0;
  String? get iniciadoPor => j['iniciado_por'] as String?;
  String get grabacion => j['grabacion_estado'].toString();
  int? get grabacionSegundos => (j['grabacion_segundos'] as num?)?.toInt();
  String? get grabacionError => j['grabacion_error'] as String?;
  String? get motivoCorte => j['motivo_corte'] as String?;
}

class VarianteLive {
  VarianteLive(this.j);
  final Map<String, dynamic> j;

  int get tallaId => j['talla_id'] as int;
  int get colorId => j['color_id'] as int;
  int get sucursalId => j['sucursal_id'] as int;
  String get texto => '${j['talla']} · ${j['color']} · ${j['sucursal']} (${j['stock']})';
  String get clave => '$tallaId-$colorId-$sucursalId';
}

class ProductoLive {
  ProductoLive(this.j);
  final Map<String, dynamic> j;

  int get id => j['id'] as int;
  String get nombre => j['nombre'].toString();
  double get precio => (j['precio'] as num).toDouble();
  double? get precioOriginal => (j['precio_original'] as num?)?.toDouble();
  String? get imagen => j['imagen'] as String?;
  bool get fijado => j['fijado'] == true;
  List<VarianteLive> get variantes => [for (final v in (j['variantes'] as List? ?? [])) VarianteLive(v as Map<String, dynamic>)];
}

class ComentarioLive {
  ComentarioLive(this.j);
  final Map<String, dynamic> j;

  int get id => j['id'] as int;
  int get usuarioId => j['usuario_id'] as int;
  String get usuario => j['usuario'].toString();
  String get texto => j['texto'].toString();
  DateTime get fecha => _fecha(j['fecha']);
  bool get oculto => j['oculto'] == true;
  bool get esTienda => j['es_tienda'] == true;
  // Solo en la repeticion: segundo del video en que se escribio.
  int get segundo => (j['segundo'] as num?)?.toInt() ?? 0;

  ComentarioLive ocultado() => ComentarioLive({...j, 'oculto': true});
}

class EspectadorLive {
  EspectadorLive(this.j);
  final Map<String, dynamic> j;

  int get usuarioId => j['usuario_id'] as int;
  String get nombre => j['nombre'].toString();
  bool get conectado => j['conectado'] == true;
  int get comentarios => (j['comentarios'] as num?)?.toInt() ?? 0;
  String? get bloqueo => j['bloqueo'] as String?;
}

class SalaLive {
  SalaLive(this.j);
  final Map<String, dynamic> j;

  LiveResumen get live => LiveResumen(j['live'] as Map<String, dynamic>);
  String get url => j['url'].toString();
  String get token => j['token'].toString();
  bool get vendedor => j['vendedor'] == true;
  bool get moderador => j['moderador'] == true;
  bool get silenciado => j['silenciado'] == true;
  List<ProductoLive> get productos => [for (final p in (j['productos'] as List)) ProductoLive(p as Map<String, dynamic>)];
  List<ComentarioLive> get comentarios => [for (final c in (j['comentarios'] as List)) ComentarioLive(c as Map<String, dynamic>)];
  List<EspectadorLive> get espectadores =>
      [for (final e in (j['espectadores'] as List? ?? [])) EspectadorLive(e as Map<String, dynamic>)];
}

const emojisLive = ['❤️', '🔥', '😍', '👏', '😂', '🛍️'];

class LiveApi {
  LiveApi(this._dio);
  final Dio _dio;

  Future<List<LiveResumen>> enVivo() async =>
      [for (final l in (await _dio.get('/live/en-vivo')).data as List) LiveResumen(l as Map<String, dynamic>)];

  Future<SalaLive> sala(int id) async => SalaLive((await _dio.get('/live/$id/sala')).data as Map<String, dynamic>);

  Future<ComentarioLive> comentar(int id, String texto) async =>
      ComentarioLive((await _dio.post('/live/$id/comentarios', data: {'texto': texto})).data as Map<String, dynamic>);

  Future<void> reaccionar(int id, String emoji) => _dio.post('/live/$id/reacciones', data: {'emoji': emoji});

  // ---------------------------------------------------------------- tienda

  Future<Map<String, dynamic>> estadoTienda() async => (await _dio.get('/live/tienda/estado')).data as Map<String, dynamic>;

  Future<List<Map<String, dynamic>>> productosTienda() async =>
      ((await _dio.get('/live/tienda/productos')).data as List).cast<Map<String, dynamic>>();

  Future<SalaLive> iniciar(String titulo, String descripcion, List<int> productoIds) async => SalaLive((await _dio.post(
        '/live/tienda',
        data: {'titulo': titulo, 'descripcion': descripcion.isEmpty ? null : descripcion, 'producto_ids': productoIds},
      ))
          .data as Map<String, dynamic>);

  Future<List<LiveResumen>> historial() async =>
      [for (final l in (await _dio.get('/live/tienda/historial')).data as List) LiveResumen(l as Map<String, dynamic>)];

  Future<void> grabar(int id) => _dio.post('/live/$id/grabar');

  Future<void> finalizar(int id) => _dio.post('/live/$id/finalizar');

  Future<List<ProductoLive>> fijar(int id, int? productoId) async => [
        for (final p in (await _dio.put('/live/$id/fijado', data: {'producto_id': productoId})).data as List)
          ProductoLive(p as Map<String, dynamic>)
      ];

  Future<void> ocultar(int id, int comentarioId) => _dio.post('/live/$id/comentarios/$comentarioId/ocultar');

  Future<List<EspectadorLive>> espectadores(int id) async =>
      [for (final e in (await _dio.get('/live/$id/espectadores')).data as List) EspectadorLive(e as Map<String, dynamic>)];

  Future<List<EspectadorLive>> bloquear(int id, int usuarioId, String tipo) async => [
        for (final e in (await _dio.post('/live/$id/bloqueos', data: {'usuario_id': usuarioId, 'tipo': tipo})).data as List)
          EspectadorLive(e as Map<String, dynamic>)
      ];

  Future<List<EspectadorLive>> desbloquear(int id, int usuarioId) async => [
        for (final e in (await _dio.delete('/live/$id/bloqueos/$usuarioId')).data as List) EspectadorLive(e as Map<String, dynamic>)
      ];

  Future<String> grabacion(int id) async => (await _dio.get('/live/$id/grabacion')).data['url'].toString();

  Future<List<ComentarioLive>> comentariosDelLive(int id) async =>
      [for (final c in (await _dio.get('/live/$id/comentarios')).data as List) ComentarioLive(c as Map<String, dynamic>)];

  Future<void> borrarGrabacion(int id) => _dio.delete('/live/$id/grabacion');
}

final liveApiProvider = Provider<LiveApi>((ref) => LiveApi(ref.watch(apiClientProvider).dio));

/// Lives en curso (el boton LIVE del encabezado se pone rojo si hay alguno).
class EnVivoNotifier extends StateNotifier<List<LiveResumen>> {
  EnVivoNotifier(this._api) : super(const []);
  final LiveApi _api;

  Future<List<LiveResumen>> revisar() async {
    try {
      state = await _api.enVivo();
    } catch (_) {
      // Sin conexion: queda lo ultimo que se vio.
    }
    return state;
  }
}

final enVivoProvider = StateNotifierProvider<EnVivoNotifier, List<LiveResumen>>(
  (ref) => EnVivoNotifier(ref.watch(liveApiProvider)),
);
