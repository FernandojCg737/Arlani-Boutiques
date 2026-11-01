import 'dart:convert';

/// Modelos del modo sin conexion (P4): lo mismo que `offline-db.ts` de la web,
/// leidos del backend (`/offline/paquete`, `/offline/catalogo-cliente`) o de
/// las tablas SQLite del telefono (`offline_db.dart`).

int _int(Object? v) => v is int ? v : int.parse(v.toString());
bool _bool(Object? v) => v == true || v == 1;

class VarianteLocal {
  VarianteLocal({
    required this.tallaId,
    required this.tallaCodigo,
    required this.colorId,
    required this.colorNombre,
    required this.stock,
    this.sucursalId,
  });

  final int tallaId;
  final String tallaCodigo;
  final int colorId;
  final String colorNombre;
  int stock;
  final int? sucursalId;

  factory VarianteLocal.fromJson(Map<String, dynamic> j) => VarianteLocal(
        tallaId: _int(j['talla_id']),
        tallaCodigo: j['talla_codigo'].toString(),
        colorId: _int(j['color_id']),
        colorNombre: j['color_nombre'].toString(),
        stock: _int(j['stock']),
        sucursalId: j['sucursal_id'] == null ? null : _int(j['sucursal_id']),
      );
}

class ProductoLocal {
  ProductoLocal({
    required this.productoId,
    required this.nombre,
    required this.precio,
    this.imagenUrl,
    this.categoria,
    required this.variantes,
  });

  final int productoId;
  final String nombre;
  final double precio;
  final String? imagenUrl;
  final String? categoria;
  final List<VarianteLocal> variantes;

  int get stockTotal => variantes.fold(0, (t, v) => t + v.stock);

  factory ProductoLocal.fromJson(Map<String, dynamic> j) => ProductoLocal(
        productoId: _int(j['producto_id']),
        nombre: j['nombre'].toString(),
        precio: double.parse(j['precio'].toString()),
        imagenUrl: j['imagen_url'] as String?,
        categoria: j['categoria'] as String?,
        variantes: [for (final v in j['variantes'] as List) VarianteLocal.fromJson(v as Map<String, dynamic>)],
      );
}

class SucursalLocal {
  const SucursalLocal(this.id, this.nombre);
  final int id;
  final String nombre;

  factory SucursalLocal.fromJson(Map<String, dynamic> j) => SucursalLocal(_int(j['id']), j['nombre'].toString());
}

class ClienteLocal {
  const ClienteLocal(this.id, this.nombre, this.email);
  final int id;
  final String nombre;
  final String email;
}

/// Lo que descarga el personal para su sucursal (CU11).
class PaquetePersonal {
  PaquetePersonal({
    required this.empresaId,
    required this.empresaNombre,
    required this.sucursal,
    required this.descargadoEn,
    required this.productos,
    required this.clientes,
  });

  final int empresaId;
  final String empresaNombre;
  final SucursalLocal sucursal;
  final DateTime descargadoEn;
  final List<ProductoLocal> productos;
  final List<ClienteLocal> clientes;

  factory PaquetePersonal.fromJson(Map<String, dynamic> j) => PaquetePersonal(
        empresaId: _int(j['empresa_id']),
        empresaNombre: j['empresa_nombre'].toString(),
        sucursal: SucursalLocal.fromJson(j['sucursal'] as Map<String, dynamic>),
        descargadoEn: DateTime.parse(j['descargado_en'].toString()),
        productos: [for (final p in j['productos'] as List) ProductoLocal.fromJson(p as Map<String, dynamic>)],
        clientes: [
          for (final c in j['clientes'] as List)
            ClienteLocal(_int(c['id']), c['nombre'].toString(), c['email'].toString()),
        ],
      );
}

class TiendaLocal {
  TiendaLocal({
    required this.empresaId,
    required this.nombre,
    this.logoUrl,
    required this.sucursales,
    required this.productos,
    this.aceptaContraEntrega = false,
    this.aceptaPaypal = false,
  });

  final int empresaId;
  final String nombre;
  final String? logoUrl;
  final List<SucursalLocal> sucursales;
  final List<ProductoLocal> productos;
  final bool aceptaContraEntrega;
  final bool aceptaPaypal;

  factory TiendaLocal.fromJson(Map<String, dynamic> j) => TiendaLocal(
        empresaId: _int(j['empresa_id']),
        nombre: j['nombre'].toString(),
        logoUrl: j['logo_url'] as String?,
        sucursales: [for (final s in j['sucursales'] as List) SucursalLocal.fromJson(s as Map<String, dynamic>)],
        productos: [for (final p in j['productos'] as List) ProductoLocal.fromJson(p as Map<String, dynamic>)],
        aceptaContraEntrega: _bool(j['acepta_contra_entrega']),
        aceptaPaypal: _bool(j['acepta_paypal']),
      );
}

class DireccionLocal {
  const DireccionLocal(this.id, this.alias, this.direccion);
  final int id;
  final String alias;
  final String direccion;
}

class PaypalLocal {
  const PaypalLocal({required this.id, this.cuenta, required this.autorizada, this.tiendas = const []});
  final int id;
  final String? cuenta;
  // Autorizada con Arlani: vale en cualquier tienda; si no, solo en `tiendas`.
  final bool autorizada;
  final List<int> tiendas;
}

/// Catalogo sin conexion del cliente (todas las tiendas con plan offline).
class CatalogoCliente {
  CatalogoCliente({required this.descargadoEn, required this.tiendas, this.direcciones = const [], this.paypals = const []});

  final DateTime descargadoEn;
  final List<TiendaLocal> tiendas;
  final List<DireccionLocal> direcciones;
  final List<PaypalLocal> paypals;

  factory CatalogoCliente.fromJson(Map<String, dynamic> j) => CatalogoCliente(
        descargadoEn: DateTime.parse(j['descargado_en'].toString()),
        tiendas: [for (final t in j['tiendas'] as List) TiendaLocal.fromJson(t as Map<String, dynamic>)],
        direcciones: [
          for (final d in (j['direcciones'] as List? ?? []))
            DireccionLocal(_int(d['id']), d['alias'].toString(), d['direccion'].toString()),
        ],
        paypals: [
          for (final p in (j['paypals'] as List? ?? []))
            PaypalLocal(
              id: _int(p['id']),
              cuenta: p['cuenta'] as String?,
              autorizada: _bool(p['autorizada']),
              tiendas: [for (final t in (p['tiendas'] as List? ?? [])) _int(t)],
            ),
        ],
      );
}

class ItemLocal {
  ItemLocal({
    required this.productoId,
    required this.tallaId,
    required this.colorId,
    required this.cantidad,
    required this.precio,
    required this.productoNombre,
    required this.talla,
    required this.color,
    this.empresaId,
    this.empresaNombre,
    this.sucursalId,
    this.sucursalNombre,
  });

  final int productoId;
  final int tallaId;
  final int colorId;
  int cantidad;
  final double precio;
  final String productoNombre;
  final String talla;
  final String color;
  // Cliente: de que tienda y sucursal es (puede elegir de varias a la vez).
  final int? empresaId;
  final String? empresaNombre;
  final int? sucursalId;
  final String? sucursalNombre;

  String get texto => '$cantidad× $productoNombre ($talla, $color)';
}

/// Prenda de una compra con PayPal guardado que no se cobro, y por que.
class NoPagado {
  const NoPagado(this.producto, this.talla, this.color, this.motivo);
  final String producto;
  final String talla;
  final String color;
  final String motivo;

  static List<NoPagado> deJson(Object? v) {
    final lista = v is String ? jsonDecode(v) : v;
    if (lista is! List) return const [];
    return [
      for (final n in lista)
        NoPagado(n['producto'].toString(), n['talla'].toString(), n['color'].toString(), n['motivo'].toString()),
    ];
  }
}

/// Venta, reserva o compra hecha en el telefono (CU12/CU13).
class OperacionLocal {
  OperacionLocal({
    required this.uuid,
    required this.usuarioId,
    required this.tipo,
    required this.empresaNombre,
    required this.sucursalId,
    required this.sucursalNombre,
    required this.registradaEn,
    this.clienteId,
    this.clienteNombre,
    this.facturaNombre,
    this.facturaNit,
    this.horarioAtencion,
    this.entrega,
    this.direccionId,
    this.formaPago,
    this.metodoPagoId,
    this.paypalCuenta,
    required this.items,
    required this.total,
    this.estado = 'pendiente',
    this.mensaje,
    this.ventaId,
    this.reservaId,
    this.intentos = 0,
    this.ultimoIntento,
    this.noPagados = const [],
    this.totalCobrado,
    this.cobroVisto = false,
  });

  final String uuid;
  final int usuarioId;
  final String tipo; // venta | reserva | pedido
  final String empresaNombre;
  final int sucursalId;
  final String sucursalNombre;
  final String registradaEn;
  final int? clienteId;
  final String? clienteNombre;
  final String? facturaNombre;
  final String? facturaNit;
  final String? horarioAtencion;
  final String? entrega; // retiro | envio
  final int? direccionId;
  final String? formaPago; // contra_entrega | paypal_guardado
  final int? metodoPagoId;
  final String? paypalCuenta;
  final List<ItemLocal> items;
  final double total;
  String estado;
  String? mensaje;
  int? ventaId;
  int? reservaId;
  int intentos;
  String? ultimoIntento;
  List<NoPagado> noPagados;
  String? totalCobrado;
  bool cobroVisto;

  /// Lo que viaja al servidor (el mismo contrato que usa la web).
  Map<String, dynamic> contrato() => {
        'uuid': uuid,
        'tipo': tipo,
        'sucursal_id': sucursalId,
        'registrada_en': registradaEn,
        'cliente_id': clienteId,
        'factura_nombre': facturaNombre,
        'factura_nit': facturaNit,
        'horario_atencion': horarioAtencion,
        'entrega': entrega ?? 'retiro',
        'direccion_id': direccionId,
        'forma_pago': formaPago,
        'metodo_pago_id': metodoPagoId,
        'items': [
          for (final i in items)
            {
              'producto_id': i.productoId,
              'talla_id': i.tallaId,
              'color_id': i.colorId,
              'cantidad': i.cantidad,
              'precio': i.precio.toStringAsFixed(2),
            },
        ],
      };
}

class RegistroSync {
  const RegistroSync({
    required this.fecha,
    required this.enviadas,
    required this.confirmadas,
    required this.conflictos,
    required this.rechazadas,
    required this.errores,
    required this.detalle,
  });

  final DateTime fecha;
  final int enviadas;
  final int confirmadas;
  final int conflictos;
  final int rechazadas;
  final int errores;
  final String detalle;
}

/// Etiquetas de estado (`ESTADO_OPERACION` de la web).
const estadoOperacion = <String, String>{
  'pendiente': 'Pendiente de enviar',
  'enviando': 'Enviando…',
  'confirmada': 'Confirmada',
  'conflicto': 'En conflicto',
  'rechazada': 'Rechazada',
  'resuelta': 'Resuelta por la tienda',
  'anulada': 'Anulada',
  'error': 'Se reintentará',
  'por_pagar': 'Por pagar',
  'sin_stock': 'Sin stock',
  'pagada': 'Pagada',
  'cancelada': 'Cancelada',
  'por_cobrar': 'Pago enviado',
  'pago_parcial': 'Pago no finalizado',
  'no_pagada': 'Pago no finalizado',
};

/// "hace 5 min", "hace 3 h"...
String haceTiempo(DateTime fecha) {
  final min = DateTime.now().difference(fecha).inMinutes;
  if (min < 1) return 'hace un momento';
  if (min < 60) return 'hace $min min';
  final h = (min / 60).round();
  if (h < 48) return 'hace $h h';
  return 'hace ${(h / 24).round()} días';
}
