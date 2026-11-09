/// Espejo de `ReservaAdminOut`/`DetalleReservaOut`/`ReservaPage` (backend,
/// CU10 -- GET /reservas). Cada reserva ya viene agrupada con TODOS sus
/// productos en `detalles` (una reserva = una orden, con 1 o mas items),
/// igual que la devuelve `crearDesdeCarrito` del lado cliente.
class DetalleReservaAdmin {
  const DetalleReservaAdmin({
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

  factory DetalleReservaAdmin.fromJson(Map<String, dynamic> json) {
    return DetalleReservaAdmin(
      id: json['id'] as int,
      productoNombre: json['producto_nombre'] as String,
      tallaCodigo: json['talla_codigo'] as String,
      colorNombre: json['color_nombre'] as String,
      cantidad: json['cantidad'] as int,
    );
  }
}

class ReservaAdmin {
  const ReservaAdmin({
    required this.id,
    this.numero,
    required this.clienteNombre,
    required this.clienteEmail,
    required this.sucursalNombre,
    required this.horarioAtencion,
    required this.estado,
    required this.fechaCreacion,
    required this.detalles,
  });

  final int id;
  final int? numero;
  final String clienteNombre;
  final String clienteEmail;
  final String sucursalNombre;
  final DateTime horarioAtencion;
  final String estado; // pendiente | confirmada | completada | cancelada | vencida
  final DateTime fechaCreacion;
  final List<DetalleReservaAdmin> detalles;

  bool get activa => estado == 'pendiente' || estado == 'confirmada';

  factory ReservaAdmin.fromJson(Map<String, dynamic> json) {
    return ReservaAdmin(
      id: json['id'] as int,
      numero: json['numero'] as int?,
      clienteNombre: json['cliente_nombre'] as String,
      clienteEmail: json['cliente_email'] as String,
      sucursalNombre: json['sucursal_nombre'] as String,
      horarioAtencion: DateTime.parse(json['horario_atencion'] as String),
      estado: json['estado'] as String,
      fechaCreacion: DateTime.parse(json['fecha_creacion'] as String),
      detalles: (json['detalles'] as List<dynamic>)
          .map((e) => DetalleReservaAdmin.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ReservaAdminPage {
  const ReservaAdminPage({required this.items, required this.total, required this.page, required this.pageSize});

  final List<ReservaAdmin> items;
  final int total;
  final int page;
  final int pageSize;

  int get totalPages => (total / pageSize).ceil().clamp(1, 999999);

  factory ReservaAdminPage.fromJson(Map<String, dynamic> json) {
    return ReservaAdminPage(
      items: (json['items'] as List<dynamic>).map((e) => ReservaAdmin.fromJson(e as Map<String, dynamic>)).toList(),
      total: json['total'] as int,
      page: json['page'] as int,
      pageSize: json['page_size'] as int,
    );
  }
}
