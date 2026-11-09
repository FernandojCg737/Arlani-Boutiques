/// Espejo de `CalificacionAdminOut`/`CalificacionPage` (GET /calificaciones)
/// -- CU20 admin.
class CalificacionAdmin {
  const CalificacionAdmin({
    required this.id,
    required this.ventaId,
    this.ventaNumero,
    required this.estrellas,
    this.comentario,
    required this.fecha,
    required this.clienteNombre,
    required this.clienteEmail,
    required this.sucursalNombre,
    this.empleadoNombre,
  });

  final int id;
  final int ventaId;
  final int? ventaNumero;
  final int estrellas;
  final String? comentario;
  final DateTime fecha;
  final String clienteNombre;
  final String clienteEmail;
  final String sucursalNombre;
  final String? empleadoNombre;

  factory CalificacionAdmin.fromJson(Map<String, dynamic> json) {
    return CalificacionAdmin(
      id: json['id'] as int,
      ventaId: json['venta_id'] as int,
      ventaNumero: json['venta_numero'] as int?,
      estrellas: json['estrellas'] as int,
      comentario: json['comentario'] as String?,
      fecha: DateTime.parse(json['fecha'] as String),
      clienteNombre: json['cliente_nombre'] as String,
      clienteEmail: json['cliente_email'] as String,
      sucursalNombre: json['sucursal_nombre'] as String,
      empleadoNombre: json['empleado_nombre'] as String?,
    );
  }
}

class DistribucionEstrellas {
  const DistribucionEstrellas({required this.estrellas, required this.cantidad});
  final int estrellas;
  final int cantidad;

  factory DistribucionEstrellas.fromJson(Map<String, dynamic> json) {
    return DistribucionEstrellas(estrellas: json['estrellas'] as int, cantidad: json['cantidad'] as int);
  }
}

class CalificacionResumen {
  const CalificacionResumen({required this.promedio, required this.total, required this.distribucion});

  final double promedio;
  final int total;
  final List<DistribucionEstrellas> distribucion;

  factory CalificacionResumen.fromJson(Map<String, dynamic> json) {
    return CalificacionResumen(
      promedio: num.parse(json['promedio'].toString()).toDouble(),
      total: json['total'] as int,
      distribucion: (json['distribucion'] as List<dynamic>)
          .map((e) => DistribucionEstrellas.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class CalificacionPage {
  const CalificacionPage({required this.resumen, required this.items, required this.total, required this.page, required this.pageSize});

  final CalificacionResumen resumen;
  final List<CalificacionAdmin> items;
  final int total;
  final int page;
  final int pageSize;

  int get totalPages => (total / pageSize).ceil().clamp(1, 999999);

  factory CalificacionPage.fromJson(Map<String, dynamic> json) {
    return CalificacionPage(
      resumen: CalificacionResumen.fromJson(json['resumen'] as Map<String, dynamic>),
      items: (json['items'] as List<dynamic>).map((e) => CalificacionAdmin.fromJson(e as Map<String, dynamic>)).toList(),
      total: json['total'] as int,
      page: json['page'] as int,
      pageSize: json['page_size'] as int,
    );
  }
}
