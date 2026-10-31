import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_provider.dart';

double _num(Object? v) => v == null ? 0 : num.parse(v.toString()).toDouble();
DateTime _fecha(Object v) {
  final s = v.toString();
  // Las fechas sin zona del backend estan en UTC.
  return DateTime.parse(s.endsWith('Z') || s.contains('+') ? s : '${s}Z').toLocal();
}

const _meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/// "31 oct de 2026, 3:15 PM" (como `date: "d MMM 'de' yyyy, h:mm a"` en la web).
String fechaLarga(DateTime d) {
  final h = d.hour % 12 == 0 ? 12 : d.hour % 12;
  return '${d.day} ${_meses[d.month - 1]} de ${d.year}, $h:${d.minute.toString().padLeft(2, '0')} ${d.hour < 12 ? 'AM' : 'PM'}';
}

String fechaCorta(DateTime d) => '${d.day} ${_meses[d.month - 1]} ${d.year}';

String bs(double v) => v.toStringAsFixed(2);

// ------------------------------------------------------------- direcciones

class DireccionCliente {
  DireccionCliente.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        alias = j['alias'] as String,
        direccion = j['direccion'] as String,
        referencia = j['referencia'] as String?,
        ciudad = j['ciudad'] as String?,
        latitud = _num(j['latitud']),
        longitud = _num(j['longitud']),
        predeterminada = j['predeterminada'] as bool? ?? false;

  final int id;
  final String alias;
  final String direccion;
  final String? referencia;
  final String? ciudad;
  final double latitud;
  final double longitud;
  final bool predeterminada;
}

// ------------------------------------------------------------- devoluciones

class DevolucionCliente {
  DevolucionCliente.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        ventaId = j['venta_id'] as int,
        tiendaNombre = j['tienda_nombre'] as String,
        sucursalNombre = j['sucursal_nombre'] as String,
        motivo = j['motivo'] as String,
        montoReembolso = _num(j['monto_reembolso']),
        metodoReembolso = j['metodo_reembolso'] as String,
        estado = j['estado'] as String,
        fechaSolicitud = _fecha(j['fecha_solicitud']!),
        fechaResolucion = j['fecha_resolucion'] == null ? null : _fecha(j['fecha_resolucion']!),
        observaciones = j['observaciones'] as String?,
        motivoRechazo = j['motivo_rechazo'] as String?,
        detalles = [
          for (final d in (j['detalles'] as List<dynamic>).cast<Map<String, dynamic>>())
            '${d['cantidad_devuelta']}× ${d['producto_nombre']} (${d['talla_codigo']}, ${d['color_nombre']})',
        ];

  final int id;
  final int ventaId;
  final String tiendaNombre;
  final String sucursalNombre;
  final String motivo;
  final double montoReembolso;
  final String metodoReembolso;
  final String estado;
  final DateTime fechaSolicitud;
  final DateTime? fechaResolucion;
  final String? observaciones;
  final String? motivoRechazo;
  final List<String> detalles;
}

// ------------------------------------------------------------- cambios

class MetodoCobro {
  MetodoCobro.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        tipo = j['tipo'] as String,
        nombre = j['nombre'] as String,
        instrucciones = j['instrucciones'] as String?,
        qrUrl = j['qr_url'] as String?,
        banco = j['banco'] as String?,
        numeroCuenta = j['numero_cuenta'] as String?,
        titular = j['titular'] as String?,
        tipoCuenta = j['tipo_cuenta'] as String?,
        documentoTitular = j['documento_titular'] as String?,
        requiereComprobante = j['requiere_comprobante'] as bool? ?? true;

  final int id;
  final String tipo;
  final String nombre;
  final String? instrucciones;
  final String? qrUrl;
  final String? banco;
  final String? numeroCuenta;
  final String? titular;
  final String? tipoCuenta;
  final String? documentoTitular;
  final bool requiereComprobante;
}

class CambioCliente {
  CambioCliente.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        ventaId = j['venta_id'] as int,
        estado = j['estado'] as String,
        cantidad = j['cantidad'] as int,
        sucursalNombre = j['sucursal_nombre'] as String,
        productoOriginal = j['producto_original'] as String,
        tallaOriginal = j['talla_original'] as String,
        colorOriginal = j['color_original'] as String,
        productoNuevo = j['producto_nuevo'] as String,
        tallaNueva = j['talla_nueva'] as String,
        colorNuevo = j['color_nuevo'] as String,
        diferencia = _num(j['diferencia']),
        diferenciaUsd = j['diferencia_usd'] == null ? null : _num(j['diferencia_usd']),
        motivoRechazo = j['motivo_rechazo'] as String?,
        reembolsoMetodo = j['reembolso_metodo'] as String?,
        fechaSolicitud = _fecha(j['fecha_solicitud']!),
        tiendaNombre = (j['tienda'] as Map<String, dynamic>)['nombre'] as String,
        metodos = [
          for (final m in (j['metodos'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>()) MetodoCobro.fromJson(m),
        ];

  final int id;
  final int ventaId;
  final String estado;
  final int cantidad;
  final String sucursalNombre;
  final String productoOriginal;
  final String tallaOriginal;
  final String colorOriginal;
  final String productoNuevo;
  final String tallaNueva;
  final String colorNuevo;
  final double diferencia;
  final double? diferenciaUsd;
  final String? motivoRechazo;
  final String? reembolsoMetodo;
  final DateTime fechaSolicitud;
  final String tiendaNombre;
  final List<MetodoCobro> metodos;
}

class LineaCambiable {
  LineaCambiable.fromJson(Map<String, dynamic> j)
      : itemLineaId = j['item_linea_id'] as int,
        productoNombre = j['producto_nombre'] as String,
        tallaCodigo = j['talla_codigo'] as String,
        colorNombre = j['color_nombre'] as String,
        disponibles = j['disponibles'] as int,
        precioPagado = _num(j['precio_pagado']);

  final int itemLineaId;
  final String productoNombre;
  final String tallaCodigo;
  final String colorNombre;
  final int disponibles;
  final double precioPagado;
}

class StockSucursal {
  StockSucursal.fromJson(Map<String, dynamic> j)
      : sucursalId = j['sucursal_id'] as int,
        sucursalNombre = j['sucursal_nombre'] as String,
        stock = j['stock'] as int;

  final int sucursalId;
  final String sucursalNombre;
  final int stock;
}

class VarianteCambio {
  VarianteCambio.fromJson(Map<String, dynamic> j)
      : tallaId = j['talla_id'] as int,
        tallaCodigo = j['talla_codigo'] as String,
        colorId = j['color_id'] as int,
        colorNombre = j['color_nombre'] as String,
        stock = j['stock'] as int,
        sucursales = [for (final s in (j['sucursales'] as List<dynamic>).cast<Map<String, dynamic>>()) StockSucursal.fromJson(s)];

  final int tallaId;
  final String tallaCodigo;
  final int colorId;
  final String colorNombre;
  final int stock;
  final List<StockSucursal> sucursales;
}

class PrendaCambio {
  PrendaCambio.fromJson(Map<String, dynamic> j)
      : productoId = j['producto_id'] as int,
        nombre = j['nombre'] as String,
        precio = _num(j['precio']),
        imagenUrl = j['imagen_url'] as String?,
        variantes = [for (final v in (j['variantes'] as List<dynamic>).cast<Map<String, dynamic>>()) VarianteCambio.fromJson(v)];

  final int productoId;
  final String nombre;
  final double precio;
  final String? imagenUrl;
  final List<VarianteCambio> variantes;
}

class OpcionesCambio {
  OpcionesCambio.fromJson(Map<String, dynamic> j)
      : ventaId = j['venta_id'] as int,
        plazoHasta = _fecha(j['plazo_hasta']!),
        puedeCambiar = j['puede_cambiar'] as bool,
        motivoNo = j['motivo_no'] as String?,
        tiendaNombre = j['tienda_nombre'] as String,
        sucursalId = j['sucursal_id'] as int,
        lineas = [for (final l in (j['lineas'] as List<dynamic>).cast<Map<String, dynamic>>()) LineaCambiable.fromJson(l)],
        prendas = [for (final p in (j['prendas'] as List<dynamic>).cast<Map<String, dynamic>>()) PrendaCambio.fromJson(p)];

  final int ventaId;
  final DateTime plazoHasta;
  final bool puedeCambiar;
  final String? motivoNo;
  final String tiendaNombre;
  final int sucursalId;
  final List<LineaCambiable> lineas;
  final List<PrendaCambio> prendas;
}

/// Las pestañas de "Mi cuenta" que viven en el backend: direcciones (CU11
/// envio), devoluciones y cambios de prenda. Los mismos endpoints que la web.
class CuentaRepository {
  CuentaRepository(this._dio);

  final Dio _dio;

  Future<List<DireccionCliente>> direcciones() async {
    final res = await _dio.get('/direcciones');
    return [for (final d in (res.data as List<dynamic>).cast<Map<String, dynamic>>()) DireccionCliente.fromJson(d)];
  }

  Future<DireccionCliente> guardarDireccion(Map<String, dynamic> cuerpo, {int? id}) async {
    final res = id == null ? await _dio.post('/direcciones', data: cuerpo) : await _dio.put('/direcciones/$id', data: cuerpo);
    return DireccionCliente.fromJson(res.data as Map<String, dynamic>);
  }

  Future<void> borrarDireccion(int id) => _dio.delete('/direcciones/$id');

  Future<List<DevolucionCliente>> devoluciones() async {
    final res = await _dio.get('/devoluciones/mias');
    return [for (final d in (res.data as List<dynamic>).cast<Map<String, dynamic>>()) DevolucionCliente.fromJson(d)];
  }

  Future<List<CambioCliente>> cambios() async {
    final res = await _dio.get('/cambios/mios');
    return [for (final c in (res.data as List<dynamic>).cast<Map<String, dynamic>>()) CambioCliente.fromJson(c)];
  }

  Future<OpcionesCambio> opcionesCambio(int ventaId) async {
    final res = await _dio.get('/cambios/opciones/$ventaId');
    return OpcionesCambio.fromJson(res.data as Map<String, dynamic>);
  }

  Future<CambioCliente> pedirCambio(Map<String, dynamic> cuerpo) async {
    final res = await _dio.post('/cambios', data: cuerpo);
    return CambioCliente.fromJson(res.data as Map<String, dynamic>);
  }

  Future<CambioCliente> cancelarCambio(int id) async {
    final res = await _dio.post('/cambios/$id/cancelar');
    return CambioCliente.fromJson(res.data as Map<String, dynamic>);
  }

  /// Orden de PayPal por la diferencia: (order_id, enlace para el panel).
  Future<(String, String?)> ordenDiferencia(int id) async {
    final res = await _dio.post('/cambios/$id/paypal/orden');
    final j = res.data as Map<String, dynamic>;
    return (j['order_id'] as String, j['approve_url'] as String?);
  }

  Future<CambioCliente> capturarDiferencia(int id, String orderId) async {
    final res = await _dio.post('/cambios/$id/paypal/capturar/$orderId');
    return CambioCliente.fromJson(res.data as Map<String, dynamic>);
  }

  Future<CambioCliente> comprobanteDiferencia(int id, int metodoId, String ruta, String nombre) async {
    final form = FormData.fromMap({
      'metodo_pago_id': '$metodoId',
      'file': await MultipartFile.fromFile(ruta, filename: nombre),
    });
    final res = await _dio.post('/cambios/$id/comprobante', data: form);
    return CambioCliente.fromJson(res.data as Map<String, dynamic>);
  }
}

final cuentaRepositoryProvider = Provider<CuentaRepository>((ref) => CuentaRepository(ref.watch(apiClientProvider).dio));
