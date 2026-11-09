/// Espejo de `VentaAdminOut`/`VentaPage` (GET /ventas) -- CU11 admin.
class VentaAdmin {
  const VentaAdmin({
    required this.id,
    this.numero,
    required this.tipo,
    required this.sucursalNombre,
    required this.fecha,
    required this.total,
    required this.metodoPago,
    required this.estadoPago,
    required this.clienteNombre,
    required this.clienteEmail,
    this.atendidoPorNombre,
  });

  final int id;
  final int? numero;
  final String tipo;
  final String sucursalNombre;
  final DateTime fecha;
  final double total;
  final String metodoPago;
  final String estadoPago;
  final String clienteNombre;
  final String clienteEmail;
  final String? atendidoPorNombre;

  factory VentaAdmin.fromJson(Map<String, dynamic> json) {
    return VentaAdmin(
      id: json['id'] as int,
      numero: json['numero'] as int?,
      tipo: json['tipo'] as String,
      sucursalNombre: json['sucursal_nombre'] as String,
      fecha: DateTime.parse(json['fecha'] as String),
      total: num.parse(json['total'].toString()).toDouble(),
      metodoPago: json['metodo_pago'] as String,
      estadoPago: json['estado_pago'] as String,
      clienteNombre: json['cliente_nombre'] as String,
      clienteEmail: json['cliente_email'] as String,
      atendidoPorNombre: json['atendido_por_nombre'] as String?,
    );
  }
}

class VentaAdminPage {
  const VentaAdminPage({required this.items, required this.total, required this.page, required this.pageSize});

  final List<VentaAdmin> items;
  final int total;
  final int page;
  final int pageSize;

  int get totalPages => (total / pageSize).ceil().clamp(1, 999999);

  factory VentaAdminPage.fromJson(Map<String, dynamic> json) {
    return VentaAdminPage(
      items: (json['items'] as List<dynamic>).map((e) => VentaAdmin.fromJson(e as Map<String, dynamic>)).toList(),
      total: json['total'] as int,
      page: json['page'] as int,
      pageSize: json['page_size'] as int,
    );
  }
}
