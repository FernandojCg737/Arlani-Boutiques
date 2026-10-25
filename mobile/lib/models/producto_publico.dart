import '../core/api_config.dart';

/// Espejo de `ProductoPublicoOut` (GET /productos/publico[/:id]).
class ProductoPublico {
  const ProductoPublico({
    required this.id,
    required this.nombre,
    this.descripcion,
    required this.precio,
    this.precioOriginal,
    required this.marcaNombre,
    required this.categoriaNombre,
    required this.temporadaNombre,
    required this.imagenes,
    required this.sucursalesDisponibles,
    required this.hasPhotos,
    this.tienda = '',
    this.tiendaNombre = '',
    this.tiendaLogo,
    this.tiendaColor,
    this.publico,
  });

  // Tienda que vende el producto (catalogo universal con todas las tiendas).
  final String tienda;
  final String tiendaNombre;
  final String? tiendaLogo;
  final String? tiendaColor;

  // Para quien es la prenda: mujer, hombre, ninos, bebes o unisex.
  final String? publico;

  final int id;
  final String nombre;
  final String? descripcion;
  final double precio;
  final double? precioOriginal;
  final String marcaNombre;
  final String categoriaNombre;
  final String temporadaNombre;
  final List<String> imagenes;
  final List<String> sucursalesDisponibles;

  // Habilita el boton del probador AR (CU09): mismo criterio que
  // `crear_ar_sesion` en el backend (ver productos.py) y que `hasPhotos`
  // en el frontend web -- tiene imagen AR dedicada, o al menos una foto de
  // catalogo real (URL absoluta, no la placeholder relativa generica de
  // antes de conectar el backend real).
  final bool hasPhotos;

  bool get agotado => sucursalesDisponibles.isEmpty;

  bool get tieneDescuento => precioOriginal != null && precioOriginal! > precio;

  int? get porcentajeDescuento {
    if (!tieneDescuento) return null;
    return (100 - (precio / precioOriginal! * 100)).round();
  }

  String? get imagenPrincipal => imagenes.isEmpty ? null : imagenes.first;

  factory ProductoPublico.fromJson(Map<String, dynamic> json) {
    // hasPhotos se calcula sobre las URLs CRUDAS (antes de resolveImageUrl):
    // una vez resueltas, hasta la placeholder generica queda con forma de
    // URL absoluta (resuelta contra el origen del frontend), y perderiamos
    // justo la distincion que nos interesa.
    final imagenesRaw = (json['imagenes'] as List<dynamic>? ?? []).map((e) => e.toString()).toList();

    return ProductoPublico(
      id: json['id'] as int,
      nombre: json['nombre'] as String,
      descripcion: json['descripcion'] as String?,
      precio: double.parse(json['precio'].toString()),
      precioOriginal:
          json['precio_original'] == null ? null : double.parse(json['precio_original'].toString()),
      marcaNombre: json['marca_nombre'] as String? ?? '',
      categoriaNombre: json['categoria_nombre'] as String? ?? '',
      temporadaNombre: json['temporada_nombre'] as String? ?? '',
      tienda: json['tienda'] as String? ?? '',
      tiendaNombre: json['tienda_nombre'] as String? ?? '',
      tiendaLogo: json['tienda_logo'] as String?,
      tiendaColor: json['tienda_color'] as String?,
      publico: json['publico'] as String?,
      imagenes: imagenesRaw.map(resolveImageUrl).toList(),
      sucursalesDisponibles:
          (json['sucursales_disponibles'] as List<dynamic>? ?? []).map((e) => e.toString()).toList(),
      hasPhotos: json['prenda_ar'] != null ||
          (imagenesRaw.isNotEmpty && imagenesRaw.first.startsWith('http')),
    );
  }
}
