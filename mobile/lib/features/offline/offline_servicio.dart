import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import '../../core/api_config.dart';
import '../../models/usuario.dart';
import '../auth/auth_provider.dart';
import 'offline_db.dart';
import 'offline_modelos.dart';

// Estados que todavia hay que mandar al servidor.
const porEnviar = {'pendiente', 'enviando', 'error'};
// Estados que el servidor todavia puede cambiar (el encargado resuelve el
// conflicto, la compra se paga o se queda sin stock, o se cobra el PayPal).
const _porConsultar = {'conflicto', 'por_pagar', 'sin_stock', 'por_cobrar'};
// Cobro con el PayPal guardado ya resuelto (se avisa una vez).
const cobroTerminado = {'pagada', 'pago_parcial', 'no_pagada'};
const _lote = 50;
const _reintentoCada = Duration(seconds: 15);
const _reintentosRapidos = [3, 6, 12, 24];
const _repetirError = Duration(minutes: 10);
const _personalCada = Duration(minutes: 3);
const _catalogoCada = Duration(seconds: 3);
const _personal = {'administrador', 'encargado_sucursal', 'cajero'};

/// P4 offline en el telefono: lo que en la web hacen `sincronizacion.ts`,
/// `descarga-automatica.ts`, `catalogo-cliente-auto.ts` e `imagenes-offline.ts`.
/// - CU12: guarda cada venta, reserva o compra en SQLite con su uuid y la
///   envia al volver la conexion (al instante, a los 3/6/12/24 s si el
///   servidor no responde, y cada 15 s mientras quede algo). Nunca se borra:
///   solo cambia de estado con la respuesta del servidor.
/// - CU11: el personal recibe solo los datos de sus sucursales cada 3 min;
///   el cliente, su catalogo, revisando cada 3 s una huella de pocos bytes.
///   Primero se envia lo pendiente y despues se descarga.
/// - Las fotos se guardan en el telefono para verlas sin conexion.
class OfflineServicio extends ChangeNotifier with WidgetsBindingObserver {
  OfflineServicio(this._ref) {
    WidgetsBinding.instance.addObserver(this);
    _conexion = Connectivity().onConnectivityChanged.listen(_alCambiarConexion);
    Connectivity().checkConnectivity().then(_alCambiarConexion);
    _relojReintento = Timer.periodic(_reintentoCada, (_) {
      if (enLinea && pendientes > 0) sincronizar();
    });
    _relojPersonal = Timer.periodic(_personalCada, (_) => descargarPersonal());
    _relojCatalogo = Timer.periodic(_catalogoCada, (_) => revisarCatalogo());
    _ref.listen<AuthState>(authProvider, (_, s) => _alCambiarUsuario(s.usuario), fireImmediately: true);
    _db.imagenes().then((m) {
      _imagenes.addAll(m);
      notifyListeners();
    });
  }

  final Ref _ref;
  final _db = OfflineDb.instancia;
  late final StreamSubscription<List<ConnectivityResult>> _conexion;
  late final Timer _relojReintento;
  late final Timer _relojPersonal;
  late final Timer _relojCatalogo;
  Timer? _reintento;
  int _reintentosHechos = 0;
  bool _aLaVista = true;
  ({String detalle, DateTime en})? _ultimoErrorAnotado;

  Dio get _dio => _ref.read(apiClientProvider).dio;

  Usuario? _usuario;
  bool enLinea = true;
  List<OperacionLocal> operaciones = [];
  List<RegistroSync> registro = [];
  bool sincronizando = false;
  // Para la vista: se enciende solo si la sincronizacion tarda (sin parpadeos).
  bool ocupado = false;
  String ultimoError = '';

  // Personal
  bool descargandoPersonal = false;
  bool? planOffline;
  DateTime? ultimaDescargaPersonal;

  // Cliente
  CatalogoCliente? catalogo;
  bool descargandoCatalogo = false;
  DateTime? revisadoEn;
  String? _version;

  final Map<String, String> _imagenes = {};

  int get pendientes => operaciones.where((o) => porEnviar.contains(o.estado)).length;
  int get conflictos => operaciones.where((o) => o.estado == 'conflicto').length;
  List<OperacionLocal> get porPagar =>
      operaciones.where((o) => o.tipo == 'pedido' && (o.estado == 'por_pagar' || o.estado == 'sin_stock')).toList();
  List<OperacionLocal> get cobros => operaciones
      .where((o) => o.formaPago == 'paypal_guardado' && cobroTerminado.contains(o.estado) && !o.cobroVisto)
      .toList();

  bool get _esPersonal => _usuario != null && _personal.contains(_usuario!.tipo);
  bool get _esCliente => _usuario?.tipo == 'cliente';

  /// La foto guardada en el telefono, si ya se descargo.
  File? fotoLocal(String? url) {
    final ruta = url == null ? null : _imagenes[url];
    return ruta == null ? null : File(ruta);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _aLaVista = state == AppLifecycleState.resumed;
    if (_aLaVista) {
      sincronizar();
      revisarCatalogo();
    }
  }

  void _alCambiarConexion(List<ConnectivityResult> r) {
    final ahora = r.any((x) => x != ConnectivityResult.none);
    if (ahora == enLinea) return;
    enLinea = ahora;
    notifyListeners();
    if (ahora) {
      _reintentosHechos = 0;
      sincronizar().then((_) {
        descargarPersonal();
        revisarCatalogo(forzar: catalogo == null);
      });
    }
  }

  Future<void> _alCambiarUsuario(Usuario? u) async {
    if (u?.id == _usuario?.id) {
      _usuario = u;
      return;
    }
    _usuario = u;
    operaciones = [];
    registro = [];
    catalogo = null;
    _version = null;
    planOffline = null;
    notifyListeners();
    if (u == null) return;
    await cargar();
    if (_esCliente) {
      catalogo = await _db.cliente(u.id);
      notifyListeners();
    }
    await sincronizar();
    descargarPersonal();
    revisarCatalogo(forzar: true);
  }

  Future<void> cargar() async {
    final u = _usuario;
    if (u == null) return;
    operaciones = await _db.operaciones(u.id);
    registro = await _db.registro(u.id);
    notifyListeners();
  }

  // ---------- CU12: registrar y sincronizar ----------

  Future<OperacionLocal> registrar({
    required String tipo,
    required String empresaNombre,
    required int sucursalId,
    required String sucursalNombre,
    required List<ItemLocal> items,
    int? clienteId,
    String? clienteNombre,
    String? facturaNombre,
    String? facturaNit,
    DateTime? horarioAtencion,
    String? entrega,
    int? direccionId,
    String? formaPago,
    int? metodoPagoId,
    String? paypalCuenta,
  }) async {
    final u = _usuario;
    if (u == null) throw StateError('Sin sesión');
    final op = OperacionLocal(
      uuid: const Uuid().v4(),
      usuarioId: u.id,
      tipo: tipo,
      empresaNombre: empresaNombre,
      sucursalId: sucursalId,
      sucursalNombre: sucursalNombre,
      registradaEn: DateTime.now().toUtc().toIso8601String(),
      clienteId: clienteId,
      clienteNombre: clienteNombre,
      facturaNombre: facturaNombre,
      facturaNit: facturaNit,
      horarioAtencion: horarioAtencion?.toUtc().toIso8601String(),
      entrega: entrega,
      direccionId: direccionId,
      formaPago: formaPago,
      metodoPagoId: metodoPagoId,
      paypalCuenta: paypalCuenta,
      items: items,
      total: items.fold(0.0, (t, i) => t + i.precio * i.cantidad),
    );
    await _db.nuevaOperacion(op);
    await cargar();
    if (enLinea) sincronizar();
    return op;
  }

  Future<void> marcarCobrosVistos() async {
    for (final o in cobros) {
      o.cobroVisto = true;
      await _db.actualizarOperacion(o);
    }
    await cargar();
  }

  Future<void> sincronizar() async {
    final u = _usuario;
    if (sincronizando || u == null || !enLinea) return;
    final enviar = operaciones.where((o) => porEnviar.contains(o.estado)).toList();
    final consultar = operaciones.where((o) => _porConsultar.contains(o.estado)).toList();
    if (enviar.isEmpty && consultar.isEmpty) return;

    sincronizando = true;
    final aviso = Timer(const Duration(milliseconds: 600), () {
      ocupado = true;
      notifyListeners();
    });
    var enviadas = 0, confirmadas = 0, enConflicto = 0, rechazadas = 0, errores = 0;
    try {
      for (var i = 0; i < enviar.length; i += _lote) {
        final lote = enviar.sublist(i, i + _lote > enviar.length ? enviar.length : i + _lote);
        final ahora = DateTime.now().toUtc().toIso8601String();
        for (final o in lote) {
          o
            ..estado = 'enviando'
            ..intentos += 1
            ..ultimoIntento = ahora;
          await _db.actualizarOperacion(o);
        }
        List resultados;
        try {
          final r = await _dio.post('/offline/sincronizar', data: {'operaciones': [for (final o in lote) o.contrato()]});
          resultados = r.data as List;
        } catch (e) {
          // Sin respuesta del servidor: quedan pendientes, se reintentan.
          for (final o in lote) {
            o.estado = 'pendiente';
            await _db.actualizarOperacion(o);
          }
          ultimoError = _motivo(e);
          errores += lote.length;
          _programarReintento();
          break;
        }
        enviadas += lote.length;
        _reintentosHechos = 0;
        ultimoError = '';
        for (final o in lote) {
          final r = resultados.cast<Map>().where((x) => x['uuid'] == o.uuid).firstOrNull;
          if (r == null) continue;
          await _aplicar(o, r);
          switch (r['estado']) {
            case 'confirmada':
              confirmadas++;
            case 'conflicto':
              enConflicto++;
            case 'rechazada':
              rechazadas++;
            case 'error':
              errores++;
          }
        }
      }
      if (consultar.isNotEmpty) {
        try {
          final r = await _dio.post('/offline/estado', data: {'uuids': [for (final o in consultar) o.uuid]});
          for (final e in (r.data as List).cast<Map>()) {
            final o = consultar.where((x) => x.uuid == e['uuid']).firstOrNull;
            if (o != null && e['estado'] != o.estado) await _aplicar(o, e);
          }
        } catch (_) {
          // Se vuelve a consultar en el proximo intento.
        }
      }
    } finally {
      // Al historial: lo que llego al servidor siempre; un mismo error de
      // conexion, no en cada reintento.
      final detalle = ultimoError.isEmpty ? 'Sincronización completada.' : ultimoError;
      final anotado = _ultimoErrorAnotado;
      final repetido = enviadas == 0 &&
          anotado != null &&
          anotado.detalle == detalle &&
          DateTime.now().difference(anotado.en) < _repetirError;
      if ((enviadas > 0 || errores > 0) && !repetido) {
        await _db.registrar(
          u.id,
          RegistroSync(
            fecha: DateTime.now(),
            enviadas: enviadas,
            confirmadas: confirmadas,
            conflictos: enConflicto,
            rechazadas: rechazadas,
            errores: errores,
            detalle: detalle,
          ),
        );
        if (enviadas == 0) _ultimoErrorAnotado = (detalle: detalle, en: DateTime.now());
      }
      aviso.cancel();
      ocupado = false;
      sincronizando = false;
      await cargar();
    }
  }

  void _programarReintento() {
    if (_reintento != null || _reintentosHechos >= _reintentosRapidos.length) return;
    _reintento = Timer(Duration(seconds: _reintentosRapidos[_reintentosHechos++]), () {
      _reintento = null;
      sincronizar();
    });
  }

  Future<void> _aplicar(OperacionLocal o, Map r) async {
    o
      ..estado = r['estado'].toString()
      ..mensaje = r['mensaje'] as String?
      ..ventaId = (r['venta_id'] as int?) ?? o.ventaId
      ..reservaId = (r['reserva_id'] as int?) ?? o.reservaId
      ..noPagados = NoPagado.deJson(r['no_pagados'])
      ..totalCobrado = r['total_cobrado']?.toString();
    await _db.actualizarOperacion(o);
  }

  String _motivo(Object e) {
    if (e is DioException) {
      final code = e.response?.statusCode;
      if (e.response == null || code == 504) return 'Sin conexión con el servidor: se reintentará.';
      if (code == 401) return 'Tu sesión venció: inicia sesión para terminar de sincronizar (tus operaciones siguen guardadas).';
      final detalle = (e.response?.data is Map) ? (e.response!.data as Map)['detail'] : null;
      if (detalle is String) return detalle;
    }
    return 'No se pudo sincronizar: se reintentará.';
  }

  // ---------- CU11: descargas ----------

  /// Lo vendido o reservado que todavia no llego al servidor sigue descontado.
  void _descontar(List<ProductoLocal> productos, Iterable<OperacionLocal> ops, {bool porSucursal = false}) {
    final usados = <String, int>{};
    for (final o in ops.where((o) => porEnviar.contains(o.estado))) {
      for (final i in o.items) {
        final k = '${i.productoId}-${i.tallaId}-${i.colorId}${porSucursal ? '-${o.sucursalId}' : ''}';
        usados[k] = (usados[k] ?? 0) + i.cantidad;
      }
    }
    if (usados.isEmpty) return;
    for (final pr in productos) {
      for (final v in pr.variantes) {
        final usado = usados['${pr.productoId}-${v.tallaId}-${v.colorId}${porSucursal ? '-${v.sucursalId}' : ''}'] ?? 0;
        if (usado > 0) v.stock = v.stock - usado < 0 ? 0 : v.stock - usado;
      }
    }
  }

  /// Sucursales donde el personal puede vender (o las ya descargadas, sin conexion).
  Future<List<SucursalLocal>> sucursalesPersonal() async {
    final u = _usuario;
    if (u == null) return [];
    try {
      final r = await _dio.get('/ventas/presencial/sucursales');
      return [for (final s in (r.data as List).cast<Map<String, dynamic>>()) SucursalLocal.fromJson(s)];
    } catch (_) {
      return _db.sucursalesDescargadas(u.id);
    }
  }

  Future<PaquetePersonal?> paquetePersonal(int sucursalId) async {
    final u = _usuario;
    return u == null ? null : _db.personal(u.id, sucursalId);
  }

  /// Descarga automatica (cada 3 min) o con el boton (`sucursalId`).
  Future<void> descargarPersonal({int? sucursalId}) async {
    final u = _usuario;
    if (!_esPersonal || u == null || descargandoPersonal || !enLinea || !_aLaVista) return;
    if (!u.hasPermiso('2P-CU11')) return;
    descargandoPersonal = true;
    notifyListeners();
    try {
      await sincronizar();
      if (planOffline == null) {
        final r = await _dio.get('/ventas/origenes');
        planOffline = (r.data as Map)['offline'] == true;
      }
      if (planOffline != true) return;
      final sucursales = sucursalId != null ? [SucursalLocal(sucursalId, '')] : await sucursalesPersonal();
      for (final s in sucursales) {
        final r = await _dio.get('/offline/paquete',
            queryParameters: {'sucursal_id': s.id, if (sucursalId == null) 'automatica': true});
        final pq = PaquetePersonal.fromJson(r.data as Map<String, dynamic>);
        _descontar(pq.productos, operaciones.where((o) => o.sucursalId == s.id));
        await _db.guardarPersonal(u.id, pq);
        _descargarFotos(pq.productos.map((x) => x.imagenUrl));
      }
      ultimaDescargaPersonal = DateTime.now();
    } catch (e) {
      // Sin conexion o el servidor no respondio: se intenta en la proxima vuelta.
      if (sucursalId != null) rethrow;
    } finally {
      descargandoPersonal = false;
      notifyListeners();
    }
  }

  /// Catalogo del cliente: pregunta la huella y solo si cambio lo descarga.
  /// `forzar`: el boton "Actualizar catalogo" (descarga aunque no cambie).
  Future<void> revisarCatalogo({bool forzar = false}) async {
    final u = _usuario;
    if (!_esCliente || u == null || descargandoCatalogo || !enLinea || !_aLaVista) return;
    if (!u.hasPermiso('CU10')) return;
    descargandoCatalogo = true;
    if (forzar) notifyListeners();
    try {
      final v = await _dio.get('/offline/catalogo-cliente/version');
      revisadoEn = DateTime.now();
      final version = (v.data as Map)['version']?.toString();
      if (!forzar && version == _version && catalogo != null) {
        // Sin cambios: solo se completan las fotos que no se alcanzaron a bajar.
        _descargarFotos(catalogo!.tiendas.expand((t) => t.productos).map((x) => x.imagenUrl));
        return;
      }
      final r = await _dio.get('/offline/catalogo-cliente', queryParameters: {'automatica': !forzar});
      if (_usuario?.id != u.id) return;
      final c = CatalogoCliente.fromJson(r.data as Map<String, dynamic>);
      for (final t in c.tiendas) {
        _descontar(t.productos, operaciones, porSucursal: true);
      }
      await _db.guardarCliente(u.id, c);
      _version = version;
      catalogo = c;
      _descargarFotos(c.tiendas.expand((t) => t.productos).map((x) => x.imagenUrl));
    } catch (e) {
      if (forzar) rethrow;
    } finally {
      descargandoCatalogo = false;
      notifyListeners();
    }
  }

  bool _bajandoFotos = false;

  /// Baja de a 4 las fotos que faltan; las que fallan se reintentan en la
  /// proxima revision.
  Future<void> _descargarFotos(Iterable<String?> urls) async {
    if (_bajandoFotos) return;
    final faltan = urls.whereType<String>().where((u) => u.isNotEmpty && !_imagenes.containsKey(u)).toList();
    if (faltan.isEmpty) return;
    _bajandoFotos = true;
    try {
      final carpeta = Directory(p.join((await getApplicationSupportDirectory()).path, 'offline_fotos'));
      await carpeta.create(recursive: true);
      Future<void> bajar(String url) async {
        try {
          final ruta = p.join(carpeta.path, '${url.hashCode.toUnsigned(32)}${p.extension(Uri.parse(url).path)}');
          await Dio().download(resolveImageUrl(url), ruta);
          await _db.guardarImagen(url, ruta);
          _imagenes[url] = ruta;
        } catch (_) {
          // Se intenta en la proxima revision.
        }
      }

      for (var i = 0; i < faltan.length; i += 4) {
        if (!enLinea) break;
        await Future.wait(faltan.skip(i).take(4).map(bajar));
      }
    } finally {
      _bajandoFotos = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _conexion.cancel();
    _relojReintento.cancel();
    _relojPersonal.cancel();
    _relojCatalogo.cancel();
    _reintento?.cancel();
    super.dispose();
  }
}

final offlineProvider = ChangeNotifierProvider<OfflineServicio>((ref) => OfflineServicio(ref));
