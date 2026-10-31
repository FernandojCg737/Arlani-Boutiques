/// Espejo de `VentaOut`/`DetalleVentaOut` (backend, CU11 -- GET /ventas/mias).
class DetalleVenta {
  const DetalleVenta({
    required this.id,
    required this.productoNombre,
    required this.tallaCodigo,
    required this.colorNombre,
    required this.cantidad,
    required this.precioUnitario,
  });

  final int id;
  final String productoNombre;
  final String tallaCodigo;
  final String colorNombre;
  final int cantidad;
  final double precioUnitario;

  factory DetalleVenta.fromJson(Map<String, dynamic> json) {
    return DetalleVenta(
      id: json['id'] as int,
      productoNombre: json['producto_nombre'] as String,
      tallaCodigo: json['talla_codigo'] as String,
      colorNombre: json['color_nombre'] as String,
      cantidad: json['cantidad'] as int,
      precioUnitario: num.parse(json['precio_unitario'].toString()).toDouble(),
    );
  }
}

class Venta {
  const Venta({
    required this.id,
    required this.tipo,
    required this.sucursalNombre,
    required this.fecha,
    required this.total,
    required this.metodoPago,
    required this.estadoPago,
    required this.detalles,
    this.calificacionEstrellas,
    this.calificacionComentario,
    this.tieneDevolucion = false,
    this.estadoDevolucion,
    this.montoDevolucion,
    this.puedeDevolver = false,
    this.puedeCambiar = false,
    this.tiendaColor,
    this.horasRestantesDevolucion,
  });

  final int id;
  final String tipo; // venta_presencial | venta_digital
  final String sucursalNombre;
  final DateTime fecha;
  final double total;
  final String metodoPago;
  final String estadoPago; // pendiente | verificando | completado | rechazado
  final List<DetalleVenta> detalles;
  final int? calificacionEstrellas;
  final String? calificacionComentario;
  final bool tieneDevolucion;
  final String? estadoDevolucion; // solicitada | completada | rechazada
  final double? montoDevolucion;
  final bool puedeDevolver;
  /// Puede cambiar una prenda (hasta 24 h despues de comprar).
  final bool puedeCambiar;
  /// Color de la tienda que vendio (sus botones en cambios y devoluciones).
  final String? tiendaColor;
  final double? horasRestantesDevolucion;

  bool get completada => estadoPago == 'completado';
  bool get calificada => calificacionEstrellas != null;

  String get tiempoRestanteDevolucion {
    if (horasRestantesDevolucion != null) {
      final h = horasRestantesDevolucion!.floor();
      final m = ((horasRestantesDevolucion! - h) * 60).round();
      return '${h}h ${m}m';
    }
    final diffMs = fecha.toUtc().add(const Duration(hours: 24)).difference(DateTime.now().toUtc()).inMinutes;
    if (diffMs <= 0) return '0h';
    final h = diffMs ~/ 60;
    final m = diffMs % 60;
    return '${h}h ${m}m';
  }

  factory Venta.fromJson(Map<String, dynamic> json) {
    return Venta(
      id: json['id'] as int,
      tipo: json['tipo'] as String,
      sucursalNombre: json['sucursal_nombre'] as String,
      fecha: DateTime.parse(json['fecha'] as String),
      total: num.parse(json['total'].toString()).toDouble(),
      metodoPago: json['metodo_pago'] as String,
      estadoPago: json['estado_pago'] as String,
      detalles: (json['detalles'] as List<dynamic>).map((e) => DetalleVenta.fromJson(e as Map<String, dynamic>)).toList(),
      calificacionEstrellas: json['calificacion_estrellas'] as int?,
      calificacionComentario: json['calificacion_comentario'] as String?,
      tieneDevolucion: json['tiene_devolucion'] as bool? ?? false,
      estadoDevolucion: json['estado_devolucion'] as String?,
      montoDevolucion: json['monto_devolucion'] != null ? num.parse(json['monto_devolucion'].toString()).toDouble() : null,
      puedeDevolver: json['puede_devolver'] as bool? ?? false,
      puedeCambiar: json['puede_cambiar'] as bool? ?? false,
      tiendaColor: (json['tienda'] as Map<String, dynamic>?)?['color_marca'] as String?,
      horasRestantesDevolucion: json['horas_restantes_devolucion'] != null ? num.parse(json['horas_restantes_devolucion'].toString()).toDouble() : null,
    );
  }
}
