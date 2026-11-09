/// Espejo de `BitacoraItem`/`BitacoraPage` (GET /bitacora) — CU17.
class BitacoraItem {
  const BitacoraItem({
    required this.id,
    required this.usuarioId,
    required this.usuarioNombre,
    required this.usuarioEmail,
    required this.accion,
    required this.entidadAfectada,
    this.entidadId,
    this.entidadNumero,
    required this.fecha,
    this.detalle,
    this.ipAddress,
    this.plataforma,
  });

  final int id;
  final int usuarioId;
  final String usuarioNombre;
  final String usuarioEmail;
  final String accion;
  final String entidadAfectada;
  final int? entidadId;
  final int? entidadNumero;
  final DateTime fecha;
  final String? detalle;
  final String? ipAddress;
  final String? plataforma;

  factory BitacoraItem.fromJson(Map<String, dynamic> json) {
    return BitacoraItem(
      id: json['id'] as int,
      usuarioId: json['usuario_id'] as int,
      usuarioNombre: json['usuario_nombre'] as String,
      usuarioEmail: json['usuario_email'] as String,
      accion: json['accion'] as String,
      entidadAfectada: json['entidad_afectada'] as String,
      entidadId: json['entidad_id'] as int?,
      entidadNumero: json['entidad_numero'] as int?,
      fecha: DateTime.parse(json['fecha'] as String),
      detalle: json['detalle'] as String?,
      ipAddress: json['ip_address'] as String?,
      plataforma: json['plataforma'] as String?,
    );
  }
}

class BitacoraPage {
  const BitacoraPage({required this.items, required this.total, required this.page, required this.pageSize});

  final List<BitacoraItem> items;
  final int total;
  final int page;
  final int pageSize;

  int get totalPages => (total / pageSize).ceil().clamp(1, 999999);

  factory BitacoraPage.fromJson(Map<String, dynamic> json) {
    return BitacoraPage(
      items: (json['items'] as List<dynamic>).map((e) => BitacoraItem.fromJson(e as Map<String, dynamic>)).toList(),
      total: json['total'] as int,
      page: json['page'] as int,
      pageSize: json['page_size'] as int,
    );
  }
}
