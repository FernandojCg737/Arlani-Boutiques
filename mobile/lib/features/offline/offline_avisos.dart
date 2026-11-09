import 'dart:ui' show Color;

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'offline_modelos.dart';

/// Notificaciones del telefono con el resultado de lo hecho sin conexion
/// (reservas, compras y ventas), apenas el servidor responde: con la app
/// abierta o desde la tarea en segundo plano. Al tocarla se abre la app:
/// - exito: Mis reservas / Mis compras (el personal: "Trabajar sin conexion").
/// - compra registrada que falta pagar: "Compras por pagar".
/// - falla: "Sin conexion", donde esta la operacion con el motivo.
final _plugin = FlutterLocalNotificationsPlugin();
bool _listo = false;

/// Quien abre la ruta al tocar una notificacion (lo pone `main.dart`).
void Function(String ruta)? alTocarNotificacion;

const _canal = AndroidNotificationDetails(
  'arlani_sin_conexion',
  'Reservas y compras sin conexión',
  channelDescription: 'Resultado de lo que hiciste sin internet cuando llega a la tienda.',
  importance: Importance.high,
  priority: Priority.high,
  color: Color(0xFF121A2C),
  styleInformation: BigTextStyleInformation(''),
);

Future<void> iniciarAvisos() async {
  if (_listo) return;
  await _plugin.initialize(
    settings: const InitializationSettings(android: AndroidInitializationSettings('@mipmap/ic_launcher')),
    onDidReceiveNotificationResponse: (r) {
      final ruta = r.payload;
      if (ruta != null && ruta.isNotEmpty) alTocarNotificacion?.call(ruta);
    },
  );
  _listo = true;
}

/// La ruta de la notificacion que abrio la app (si la abrio una).
Future<String?> rutaDeInicio() async {
  await iniciarAvisos();
  final d = await _plugin.getNotificationAppLaunchDetails();
  if (d?.didNotificationLaunchApp != true) return null;
  return d!.notificationResponse?.payload;
}

/// Android 13+: pide el permiso la primera vez que se guarda algo sin conexion.
Future<void> pedirPermisoAvisos() async {
  try {
    await iniciarAvisos();
    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
  } catch (_) {}
}

/// Guardada sin internet: queda en el telefono y se envia sola al volver.
Future<void> avisarGuardadaSinConexion(OperacionLocal o, {required bool personal}) async {
  final que = switch (o.tipo) { 'pedido' => 'Compra', 'venta' => 'Venta', _ => 'Reserva' };
  try {
    await iniciarAvisos();
    await _plugin.show(
      id: o.uuid.hashCode & 0x7fffffff,
      title: '$que guardada sin conexión',
      body: '${o.empresaNombre} · ${o.sucursalNombre}: ${o.items.map((i) => i.texto).join(', ')}. '
          'Se enviará sola a la tienda cuando vuelva internet, aunque cierres la app.',
      notificationDetails: const NotificationDetails(android: _canal),
      payload: personal ? '/admin/sin-conexion' : '/sin-conexion',
    );
  } catch (_) {}
}

// Estados que todavia no son un resultado (no se avisa).
const _sinAviso = {'pendiente', 'enviando', 'error', 'por_cobrar'};

/// Avisa el resultado si la operacion cambio a un estado que lo amerita.
Future<void> avisarResultado(OperacionLocal o, {required String antes, required bool personal}) async {
  if (o.estado == antes || _sinAviso.contains(o.estado)) return;
  final aviso = _aviso(o, personal, antes);
  if (aviso == null) return;
  try {
    await iniciarAvisos();
    await _plugin.show(
      id: o.uuid.hashCode & 0x7fffffff,
      title: aviso.titulo,
      body: aviso.cuerpo,
      notificationDetails: const NotificationDetails(android: _canal),
      payload: aviso.ruta,
    );
  } catch (_) {
    // Sin permiso de notificaciones: el resultado igual se ve en la app.
  }
}

({String titulo, String cuerpo, String ruta})? _aviso(OperacionLocal o, bool personal, String antes) {
  final que = switch (o.tipo) { 'pedido' => 'Compra', 'venta' => 'Venta', _ => 'Reserva' };
  final prendas = o.items.map((i) => i.texto).join(', ');
  final lugar = '${o.empresaNombre} · ${o.sucursalNombre}';
  final total = 'Bs ${(double.tryParse(o.totalCobrado ?? '') ?? o.total).toStringAsFixed(2).replaceAll('.', ',')}';
  final motivo = (o.mensaje ?? '').trim();
  final fallaRuta = personal ? '/admin/sin-conexion' : '/sin-conexion';
  String exitoRuta(String tab) => personal ? '/admin/sin-conexion' : '/perfil?tab=$tab';

  switch (o.estado) {
    case 'confirmada':
    case 'resuelta':
      final tab = o.tipo == 'reserva' ? 'reservas' : 'compras';
      final numero = o.reservaId != null
          ? ' #${o.reservaNumero ?? o.reservaId}'
          : (o.ventaId != null ? ' #${o.ventaNumero ?? o.ventaId}' : '');
      return (
        titulo: o.estado == 'resuelta' ? '$que resuelta por la tienda' : '$que realizada con éxito',
        cuerpo: '$que$numero en $lugar: $prendas. Total $total.'
            '${o.tipo == 'reserva' && o.horarioAtencion != null ? ' Recógela hasta ${_fecha(o.horarioAtencion!)}.' : ''}',
        ruta: exitoRuta(tab),
      );
    case 'pagada':
      return (
        titulo: 'Compra realizada con éxito',
        cuerpo: '${antes == 'en_espera' ? 'Volvió a haber stock. ' : ''}'
            'Compra${o.ventaId != null ? ' #${o.ventaNumero ?? o.ventaId}' : ''} en $lugar: $prendas. '
            '${o.formaPago == 'contra_entrega' ? 'Total $total: pagas ${o.entrega == 'envio' ? 'al recibirla' : 'al recogerla'}.' : 'Pagaste $total${o.formaPago == 'paypal_guardado' ? ' con tu PayPal' : ''}.'}',
        ruta: exitoRuta('compras'),
      );
    case 'en_espera':
      return (
        titulo: 'Compra en espera de stock',
        cuerpo: '$lugar: $prendas. No hay stock suficiente por ahora: quedaste en la cola y tu compra se completa '
            'sola cuando vuelva (hasta 7 días). No se te cobró nada; puedes cancelarla.',
        ruta: personal ? fallaRuta : '/pagar-compras',
      );
    case 'cancelada':
      // Solo la que se cancelo sola por la cola (la que cancela el cliente no se avisa).
      if (!motivo.contains('No volvió a haber stock')) return null;
      return (
        titulo: 'Tu compra se canceló',
        cuerpo: '$lugar: $prendas. No volvió a haber stock en 7 días. No se te cobró nada.',
        ruta: fallaRuta,
      );
    case 'por_pagar' when antes == 'en_espera' || antes == 'por_cobrar':
      return (
        titulo: motivo.contains('subió el precio') || motivo.contains('Subió el precio')
            ? 'Volvió el stock, pero subió el precio'
            : 'Volvió a haber stock',
        cuerpo: '$lugar: $prendas. ${motivo.isEmpty ? 'Ya puedes pagarla.' : motivo} No se te cobró nada todavía.',
        ruta: personal ? fallaRuta : '/pagar-compras',
      );
    case 'por_pagar':
      return (
        titulo: 'Tu compra llegó a la tienda: falta pagarla',
        cuerpo: '$lugar: $prendas. Total $total. Toca para revisar el precio y el stock de ahora y pagarla.',
        ruta: personal ? fallaRuta : '/pagar-compras',
      );
    case 'pago_parcial':
      final noPagadas = o.noPagados.map((n) => '${n.producto} (${n.talla}, ${n.color}): ${n.motivo}').join('; ');
      return (
        titulo: 'Compra pagada en parte',
        cuerpo: '$lugar: se cobró solo lo disponible ($total). No se pudo pagar: $noPagadas.',
        ruta: fallaRuta,
      );
    case 'no_pagada':
    case 'sin_stock':
    case 'conflicto':
    case 'rechazada':
    case 'anulada':
      final titulo = switch (o.estado) {
        'conflicto' => 'Tu ${que.toLowerCase()} tiene un problema de stock',
        'anulada' => 'La tienda anuló tu ${que.toLowerCase()}',
        _ => 'No se pudo completar tu ${que.toLowerCase()}',
      };
      return (
        titulo: titulo,
        cuerpo: '$lugar: $prendas.${motivo.isEmpty ? '' : ' Motivo: $motivo'} Toca para ver el detalle.',
        ruta: fallaRuta,
      );
  }
  return null;
}

String _fecha(String iso) {
  final d = DateTime.parse(iso).toLocal();
  String dos(int n) => n.toString().padLeft(2, '0');
  return '${dos(d.day)}/${dos(d.month)} ${dos(d.hour)}:${dos(d.minute)}';
}
