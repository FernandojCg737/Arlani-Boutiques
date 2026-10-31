import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_provider.dart';
import '../cuenta/cuenta_repository.dart' show MetodoCobro;

double _num(Object? v) => v == null ? 0 : num.parse(v.toString()).toDouble();

class ItemTienda {
  ItemTienda.fromJson(Map<String, dynamic> j)
      : detalleId = j['detalle_id'] as int,
        productoNombre = j['producto_nombre'] as String,
        tallaCodigo = j['talla_codigo'] as String,
        colorNombre = j['color_nombre'] as String,
        sucursalId = j['sucursal_id'] as int,
        sucursalNombre = j['sucursal_nombre'] as String,
        cantidad = j['cantidad'] as int,
        subtotal = _num(j['subtotal']);

  final int detalleId;
  final String productoNombre;
  final String tallaCodigo;
  final String colorNombre;
  final int sucursalId;
  final String sucursalNombre;
  final int cantidad;
  final double subtotal;
}

/// Lo del carrito de UNA tienda, con sus metodos de pago (`TiendaCheckout`).
class TiendaCheckout {
  TiendaCheckout.fromJson(Map<String, dynamic> j)
      : empresaId = j['empresa_id'] as int,
        nombre = j['nombre'] as String,
        logoUrl = j['logo_url'] as String?,
        colorMarca = (j['color_marca'] as String?) ?? '#1f2a44',
        operativa = j['operativa'] as bool? ?? true,
        items = [for (final i in (j['items'] as List<dynamic>).cast<Map<String, dynamic>>()) ItemTienda.fromJson(i)],
        total = _num(j['total']),
        totalUsd = _num(j['total_usd']),
        metodos = [for (final m in (j['metodos'] as List<dynamic>).cast<Map<String, dynamic>>()) MetodoCobro.fromJson(m)],
        aceptaPagarTodo = j['acepta_pagar_todo'] as bool? ?? false;

  final int empresaId;
  final String nombre;
  final String? logoUrl;
  final String colorMarca;
  final bool operativa;
  final List<ItemTienda> items;
  final double total;
  final double totalUsd;
  final List<MetodoCobro> metodos;
  final bool aceptaPagarTodo;

  List<String> get sucursales => {for (final i in items) i.sucursalNombre}.toList();
}

class StockItem {
  StockItem.fromJson(Map<String, dynamic> j)
      : detalleId = j['detalle_id'] as int,
        productoNombre = j['producto_nombre'] as String,
        tallaCodigo = j['talla_codigo'] as String,
        colorNombre = j['color_nombre'] as String,
        sucursalNombre = j['sucursal_nombre'] as String,
        pedida = j['cantidad_pedida'] as int,
        disponibleCantidad = j['cantidad_disponible'] as int,
        disponible = j['disponible'] as bool;

  final int detalleId;
  final String productoNombre;
  final String tallaCodigo;
  final String colorNombre;
  final String sucursalNombre;
  final int pedida;
  final int disponibleCantidad;
  final bool disponible;
}

class VentaCreada {
  VentaCreada.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        sucursalNombre = j['sucursal_nombre'] as String,
        tiendaNombre = (j['tienda'] as Map<String, dynamic>?)?['nombre'] as String?,
        tiendaColor = (j['tienda'] as Map<String, dynamic>?)?['color_marca'] as String?;

  final int id;
  final String sucursalNombre;
  final String? tiendaNombre;
  final String? tiendaColor;
}

class EstadoSucursal {
  const EstadoSucursal(this.abierta, this.horario);

  final bool abierta;
  final String? horario;
}

/// Checkout por tienda (`/ventas/checkout/...`, los mismos endpoints que la
/// web): cada tienda se paga por separado con sus metodos, o todo junto.
class CheckoutRepository {
  CheckoutRepository(this._dio);

  final Dio _dio;
  static const _base = '/ventas/checkout';

  List<VentaCreada> _ventas(Response res) =>
      [for (final v in (res.data as List<dynamic>).cast<Map<String, dynamic>>()) VentaCreada.fromJson(v)];

  Map<String, dynamic>? _envio(int? direccionId) => direccionId == null ? null : {'direccion_id': direccionId};

  Future<List<TiendaCheckout>> tiendas() async {
    final res = await _dio.get('$_base/tiendas');
    return [for (final t in (res.data as List<dynamic>).cast<Map<String, dynamic>>()) TiendaCheckout.fromJson(t)];
  }

  Future<List<StockItem>> verificarStock() async {
    final res = await _dio.get('$_base/verificar-stock');
    return [for (final s in (res.data as List<dynamic>).cast<Map<String, dynamic>>()) StockItem.fromJson(s)];
  }

  Future<EstadoSucursal> estadoSucursal(int id) async {
    final res = await _dio.get('/cajas/sucursal/$id/estado');
    final j = res.data as Map<String, dynamic>;
    return EstadoSucursal(j['abierta'] as bool? ?? true, j['horario_atencion'] as String?);
  }

  /// Orden de PayPal de una tienda (o de todo junto si [empresaId] es null):
  /// (order_id, enlace para el panel). Con PayPal se guarda la cuenta.
  Future<(String, String?)> orden(int? empresaId) async {
    final ruta = empresaId == null ? '$_base/todo/paypal/orden' : '$_base/tienda/$empresaId/paypal/orden';
    final res = await _dio.post(ruta, data: {'guardar_paypal': true});
    final j = res.data as Map<String, dynamic>;
    return (j['order_id'] as String, j['approve_url'] as String?);
  }

  Future<List<VentaCreada>> capturar(int? empresaId, String orderId, int? direccionId) async {
    final ruta = empresaId == null ? '$_base/todo/paypal/capturar/$orderId' : '$_base/tienda/$empresaId/paypal/capturar/$orderId';
    return _ventas(await _dio.post(ruta, queryParameters: _envio(direccionId)));
  }

  Future<List<VentaCreada>> comprobante(int empresaId, int metodoId, String ruta, String nombre, int? direccionId) async {
    final form = FormData.fromMap({
      'metodo_pago_id': '$metodoId',
      'direccion_id': ?direccionId?.toString(),
      'file': await MultipartFile.fromFile(ruta, filename: nombre),
    });
    return _ventas(await _dio.post('$_base/tienda/$empresaId/comprobante', data: form));
  }
}

final checkoutRepositoryProvider = Provider<CheckoutRepository>((ref) => CheckoutRepository(ref.watch(apiClientProvider).dio));
