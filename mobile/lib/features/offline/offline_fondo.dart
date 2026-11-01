import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:workmanager/workmanager.dart';

import '../../core/api_config.dart';
import '../../core/secure_storage.dart';
import 'offline_avisos.dart';
import 'offline_db.dart';
import 'offline_modelos.dart';

/// P4 offline en segundo plano (lo que en la web hace el service worker con
/// Background Sync): Android (WorkManager) despierta a la app cuando vuelve
/// internet y envia las ventas, reservas y compras pendientes de SQLite,
/// aunque la app este cerrada o el cliente no la vuelva a abrir.
/// - Al guardar una operacion se agenda una tarea "cuando haya internet".
/// - Ademas, cada 15 min (el minimo de Android) se revisa por si quedo algo.
/// El servidor reconoce cada operacion por su uuid: si la app abierta y la
/// tarea la mandan las dos, no se duplica.
const _tareaEnviar = 'arlani-enviar-pendientes';
const _tareaPeriodica = 'arlani-revisar-pendientes';
final _conInternet = Constraints(networkType: NetworkType.connected);
const _porEnviar = {'pendiente', 'enviando', 'error'};
const _porConsultar = {'conflicto', 'por_pagar', 'sin_stock', 'por_cobrar'};

@pragma('vm:entry-point')
void despacharTareasFondo() {
  Workmanager().executeTask((tarea, datos) async {
    WidgetsFlutterBinding.ensureInitialized();
    try {
      return await enviarPendientesEnFondo();
    } catch (_) {
      // false: Android la reintenta mas tarde (con espera creciente).
      return false;
    }
  });
}

/// Se llama una vez al abrir la app.
Future<void> iniciarTareasFondo() async {
  await Workmanager().initialize(despacharTareasFondo);
  await Workmanager().registerPeriodicTask(
    _tareaPeriodica,
    _tareaPeriodica,
    frequency: const Duration(minutes: 15),
    constraints: _conInternet,
    existingWorkPolicy: ExistingPeriodicWorkPolicy.keep,
  );
}

/// Hay algo por enviar: Android lo manda apenas haya internet.
Future<void> agendarEnvioEnFondo() async {
  try {
    await Workmanager().registerOneOffTask(
      _tareaEnviar,
      _tareaEnviar,
      constraints: _conInternet,
      existingWorkPolicy: ExistingWorkPolicy.replace,
      backoffPolicy: BackoffPolicy.exponential,
      backoffPolicyDelay: const Duration(seconds: 30),
    );
  } catch (_) {
    // Sin WorkManager (p. ej. pruebas): se envia al abrir la app.
  }
}

/// Envia lo pendiente del usuario con sesion guardada. true = terminado (o
/// nada que hacer); false = el servidor no respondio, se reintenta.
Future<bool> enviarPendientesEnFondo() async {
  final storage = SecureStorage();
  final token = await storage.readToken();
  final usuario = await storage.readUsuario();
  if (token == null || usuario == null) return true;
  final usuarioId = usuario['id'] as int;
  final db = OfflineDb.instancia;
  final todas = await db.operaciones(usuarioId);
  final pendientes = todas.where((o) => _porEnviar.contains(o.estado)).toList();
  // Lo que todavia decide la tienda (conflicto, por pagar, cobro con PayPal).
  final porConsultar = todas.where((o) => _porConsultar.contains(o.estado)).toList();
  if (pendientes.isEmpty && porConsultar.isEmpty) return true;
  final personal = usuario['tipo'] != 'cliente';

  final dio = Dio(BaseOptions(
    baseUrl: apiBaseUrl,
    // El servidor puede estar dormido (Render): se le da tiempo.
    connectTimeout: const Duration(seconds: 60),
    receiveTimeout: const Duration(seconds: 60),
    headers: {'Authorization': 'Bearer $token', 'X-Client-Platform': 'movil'},
  ));
  var enviadas = 0, confirmadas = 0, conflictos = 0, rechazadas = 0, errores = 0;
  var detalle = 'Sincronización en segundo plano completada.';
  var terminado = true;
  for (var i = 0; i < pendientes.length; i += 50) {
    final lote = pendientes.sublist(i, i + 50 > pendientes.length ? pendientes.length : i + 50);
    final ahora = DateTime.now().toUtc().toIso8601String();
    for (final o in lote) {
      o
        ..intentos += 1
        ..ultimoIntento = ahora;
    }
    Response<dynamic> r;
    try {
      r = await dio.post('/offline/sincronizar', data: {'operaciones': [for (final o in lote) o.contrato()]});
    } on DioException catch (e) {
      // Las operaciones siguen pendientes (nunca se borran por enviarlas).
      for (final o in lote) {
        await db.actualizarOperacion(o..estado = 'pendiente');
      }
      errores += lote.length;
      // 401: la sesion vencio; se envia al volver a iniciar sesion.
      if (e.response?.statusCode == 401) {
        detalle = 'Tu sesión venció: inicia sesión para terminar de sincronizar (tus operaciones siguen guardadas).';
      } else {
        detalle = 'Sin conexión con el servidor: se reintentará.';
        terminado = false;
      }
      break;
    }
    final nuevo = r.headers.value('x-token-renovado');
    if (nuevo != null && nuevo.isNotEmpty) await storage.saveToken(nuevo);
    enviadas += lote.length;
    for (final o in lote) {
      final res = (r.data as List).cast<Map>().where((x) => x['uuid'] == o.uuid).firstOrNull;
      if (res == null) continue;
      final antes = o.estado;
      o
        ..estado = res['estado'].toString()
        ..mensaje = res['mensaje'] as String?
        ..ventaId = (res['venta_id'] as int?) ?? o.ventaId
        ..reservaId = (res['reserva_id'] as int?) ?? o.reservaId
        ..noPagados = NoPagado.deJson(res['no_pagados'])
        ..totalCobrado = res['total_cobrado']?.toString();
      await db.actualizarOperacion(o);
      // Notificacion con el resultado, aunque la app este cerrada.
      await avisarResultado(o, antes: antes, personal: personal);
      switch (o.estado) {
        case 'confirmada':
          confirmadas++;
        case 'conflicto':
          conflictos++;
        case 'rechazada':
          rechazadas++;
        case 'error':
          errores++;
          terminado = false;
      }
    }
  }
  if (porConsultar.isNotEmpty) {
    try {
      final r = await dio.post('/offline/estado', data: {'uuids': [for (final o in porConsultar) o.uuid]});
      for (final e in (r.data as List).cast<Map>()) {
        final o = porConsultar.where((x) => x.uuid == e['uuid']).firstOrNull;
        if (o == null || e['estado'] == o.estado) continue;
        final antes = o.estado;
        o
          ..estado = e['estado'].toString()
          ..mensaje = e['mensaje'] as String?
          ..ventaId = (e['venta_id'] as int?) ?? o.ventaId
          ..reservaId = (e['reserva_id'] as int?) ?? o.reservaId
          ..noPagados = NoPagado.deJson(e['no_pagados'])
          ..totalCobrado = e['total_cobrado']?.toString();
        await db.actualizarOperacion(o);
        await avisarResultado(o, antes: antes, personal: personal);
      }
    } catch (_) {
      // Se vuelve a consultar en la proxima vuelta.
    }
  }
  // Al historial solo si se envio algo (las consultas no se anotan).
  if (enviadas == 0 && errores == 0) return terminado;
  await db.registrar(
    usuarioId,
    RegistroSync(
      fecha: DateTime.now(),
      enviadas: enviadas,
      confirmadas: confirmadas,
      conflictos: conflictos,
      rechazadas: rechazadas,
      errores: errores,
      detalle: detalle,
    ),
  );
  return terminado;
}
