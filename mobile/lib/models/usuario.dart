/// Espejo de `UsuarioOut` en el backend (mismo shape que `Cliente` en la web).
class Usuario {
  const Usuario({
    required this.id,
    required this.nombre,
    this.apellidos,
    this.fotoUrl,
    required this.email,
    this.telefono,
    this.direccion,
    required this.tipo,
    this.rol,
    required this.permisos,
    this.sucursalId,
  });

  final int id;
  final String nombre;
  // CU15: parte de apellidos del nombre completo y foto de perfil.
  final String? apellidos;
  final String? fotoUrl;
  final String email;
  final String? telefono;
  final String? direccion;
  final String tipo; // cliente | administrador | encargado_sucursal | cajero
  final String? rol;
  final List<String> permisos;
  final int? sucursalId; // solo empleados; null para clientes y Administrador

  bool get isCliente => tipo == 'cliente';
  bool get isAdministrador => tipo == 'administrador';
  bool get isStaff => tipo != 'cliente';

  bool hasPermiso(String codigo) => isAdministrador || permisos.contains(codigo);

  /// Nombres y apellidos por separado: los apellidos guardados o, en cuentas
  /// viejas, las ultimas 2 palabras si son 3 o mas (la ultima si son 2).
  (String, String) get partesNombre {
    final completo = nombre.trim();
    final ap = (apellidos ?? '').trim();
    if (ap.isNotEmpty && completo.endsWith(ap)) {
      return (completo.substring(0, completo.length - ap.length).trim(), ap);
    }
    final p = completo.split(RegExp(r'\s+')).where((x) => x.isNotEmpty).toList();
    final n = p.length >= 3 ? 2 : (p.length == 2 ? 1 : 0);
    return (p.take(p.length - n).join(' '), p.skip(p.length - n).join(' '));
  }

  factory Usuario.fromJson(Map<String, dynamic> json) {
    return Usuario(
      id: json['id'] as int,
      nombre: json['nombre'] as String,
      apellidos: json['apellidos'] as String?,
      fotoUrl: json['foto_url'] as String?,
      email: json['email'] as String,
      telefono: json['telefono'] as String?,
      direccion: json['direccion'] as String?,
      tipo: json['tipo'] as String,
      rol: json['rol'] as String?,
      permisos: (json['permisos'] as List<dynamic>? ?? []).map((e) => e.toString()).toList(),
      sucursalId: json['sucursal_id'] as int?,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'nombre': nombre,
    'apellidos': apellidos,
    'foto_url': fotoUrl,
    'email': email,
    'telefono': telefono,
    'direccion': direccion,
    'tipo': tipo,
    'rol': rol,
    'permisos': permisos,
    'sucursal_id': sucursalId,
  };
}

class TokenResponse {
  const TokenResponse({required this.accessToken, required this.usuario});

  final String accessToken;
  final Usuario usuario;

  factory TokenResponse.fromJson(Map<String, dynamic> json) {
    return TokenResponse(
      accessToken: json['access_token'] as String,
      usuario: Usuario.fromJson(json['usuario'] as Map<String, dynamic>),
    );
  }
}
