import '../core/api_config.dart';

/// Espejo de `CarritoOut`/`DetalleCarritoOut` (backend, CU11). El carrito
/// ahora vive en el backend ligado al cliente -- igual que en la web desde
/// CU11, ya no es local. Pydantic serializa Decimal como texto (ej.
/// "130.00"), por eso se parsea con `num.parse` en vez de asumir `num`.
class DetalleCarrito {
  const DetalleCarrito({
    required this.id,
    required this.productoId,
    required this.productoNombre,
    this.productoImagenUrl,
    required this.tallaId,
    required this.tallaCodigo,
    required this.colorId,
    required this.colorNombre,
    required this.sucursalId,
    required this.sucursalNombre,
    required this.cantidad,
    required this.precioUnitario,
    required this.subtotal,
    this.tienda,
    this.tiendaNombre,
    this.tiendaLogo,
    this.tiendaColor,
  });

  // Boutique que vende la prenda: el carrito se agrupa por tienda.
  final String? tienda;
  final String? tiendaNombre;
  final String? tiendaLogo;
  final String? tiendaColor;

  final int id;
  final int productoId;
  final String productoNombre;
  final String? productoImagenUrl;
  final int tallaId;
  final String tallaCodigo;
  final int colorId;
  final String colorNombre;
  final int sucursalId;
  final String sucursalNombre;
  final int cantidad;
  final double precioUnitario;
  final double subtotal;

  factory DetalleCarrito.fromJson(Map<String, dynamic> json) {
    return DetalleCarrito(
      id: json['id'] as int,
      productoId: json['producto_id'] as int,
      productoNombre: json['producto_nombre'] as String,
      productoImagenUrl: (json['producto_imagen_url'] as String?) != null
          ? resolveImageUrl(json['producto_imagen_url'] as String)
          : null,
      tallaId: json['talla_id'] as int,
      tallaCodigo: json['talla_codigo'] as String,
      colorId: json['color_id'] as int,
      colorNombre: json['color_nombre'] as String,
      sucursalId: json['sucursal_id'] as int,
      sucursalNombre: json['sucursal_nombre'] as String,
      cantidad: json['cantidad'] as int,
      precioUnitario: num.parse(json['precio_unitario'].toString()).toDouble(),
      subtotal: num.parse(json['subtotal'].toString()).toDouble(),
      tienda: json['tienda'] as String?,
      tiendaNombre: json['tienda_nombre'] as String?,
      tiendaLogo: json['tienda_logo'] as String?,
      tiendaColor: json['tienda_color'] as String?,
    );
  }
}

class Carrito {
  const Carrito({required this.id, required this.estado, required this.detalles, required this.total});

  final int id;
  final String estado;
  final List<DetalleCarrito> detalles;
  final double total;

  int get totalItems => detalles.fold(0, (sum, d) => sum + d.cantidad);

  factory Carrito.fromJson(Map<String, dynamic> json) {
    return Carrito(
      id: json['id'] as int,
      estado: json['estado'] as String,
      detalles: (json['detalles'] as List<dynamic>)
          .map((e) => DetalleCarrito.fromJson(e as Map<String, dynamic>))
          .toList(),
      total: num.parse(json['total'].toString()).toDouble(),
    );
  }
}
