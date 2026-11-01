/// Espejo de `ReservaOut`/`DetalleReservaOut` (backend, CU10 --
/// GET /reservas/mias): las reservas del propio cliente.
class DetalleReserva {
  const DetalleReserva({
    required this.id,
    required this.productoNombre,
    required this.tallaCodigo,
    required this.colorNombre,
    required this.cantidad,
  });

  final int id;
  final String productoNombre;
  final String tallaCodigo;
  final String colorNombre;
  final int cantidad;

  factory DetalleReserva.fromJson(Map<String, dynamic> json) {
    return DetalleReserva(
      id: json['id'] as int,
      productoNombre: json['producto_nombre'] as String,
      tallaCodigo: json['talla_codigo'] as String,
      colorNombre: json['color_nombre'] as String,
      cantidad: json['cantidad'] as int,
    );
  }
}

class Reserva {
  const Reserva({
    required this.id,
    this.origen = 'online',
    required this.sucursalNombre,
    required this.horarioAtencion,
    required this.estado,
    required this.detalles,
  });

  final int id;
  // offline: hecha en "Sin conexion" y sincronizada despues.
  final String origen;
  final String sucursalNombre;
  final DateTime horarioAtencion;
  final String estado; // pendiente | confirmada | completada | cancelada | vencida
  final List<DetalleReserva> detalles;

  bool get cancelable => estado == 'pendiente' || estado == 'confirmada';

  factory Reserva.fromJson(Map<String, dynamic> json) {
    return Reserva(
      id: json['id'] as int,
      origen: json['origen'] as String? ?? 'online',
      sucursalNombre: json['sucursal_nombre'] as String,
      horarioAtencion: DateTime.parse(json['horario_atencion'] as String),
      estado: json['estado'] as String,
      detalles: (json['detalles'] as List<dynamic>).map((e) => DetalleReserva.fromJson(e as Map<String, dynamic>)).toList(),
    );
  }
}
