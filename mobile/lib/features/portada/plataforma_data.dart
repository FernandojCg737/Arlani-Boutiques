import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_config.dart';
import '../auth/auth_provider.dart';

/// Una tienda activa de la lista publica (GET /tiendas), igual que
/// `TiendaResumen` en `services/tienda-publica.ts`.
class TiendaResumen {
  const TiendaResumen({
    required this.id,
    required this.nombre,
    required this.subdominio,
    this.ciudad,
    required this.colorMarca,
    this.logoUrl,
  });

  final int id;
  final String nombre;
  final String subdominio;
  final String? ciudad;
  final Color colorMarca;
  final String? logoUrl;

  factory TiendaResumen.fromJson(Map<String, dynamic> json) => TiendaResumen(
        id: json['id'] as int,
        nombre: json['nombre'] as String,
        subdominio: json['subdominio'] as String,
        ciudad: json['ciudad'] as String?,
        colorMarca: colorDesdeHex(json['color_marca'] as String?),
        logoUrl: json['logo_url'] as String?,
      );
}

/// La tienda original (Atelier Aranier): en la vitrina lleva sus tres fotos.
const tiendaOriginal = 'atelier-aranier';

final tiendasProvider = FutureProvider<List<TiendaResumen>>((ref) async {
  final res = await ref.watch(apiClientProvider).dio.get('/tiendas');
  return (res.data as List<dynamic>).map((e) => TiendaResumen.fromJson(e as Map<String, dynamic>)).toList();
});

Color colorDesdeHex(String? hex, {Color porDefecto = const Color(0xFF1F2A44)}) {
  final limpio = (hex ?? '').replaceAll('#', '');
  if (limpio.length != 6) return porDefecto;
  final valor = int.tryParse(limpio, radix: 16);
  return valor == null ? porDefecto : Color(0xFF000000 | valor);
}

/// Enlace corto que se muestra en las tarjetas (`enlaceTiendaCorto` en la web):
/// el dominio publicado de la plataforma + `/tienda-<subdominio>`.
String enlaceTiendaCorto(String subdominio) {
  final host = Uri.parse(webAssetsBaseUrl).host;
  return '$host/tienda-$subdominio';
}

/// Abre la tienda de una boutique. La pagina propia de cada tienda llega en
/// el siguiente paso de la Fase 1; mientras tanto se abre el catalogo.
void abrirTienda(BuildContext context, String subdominio) => context.go('/catalogo');

/// Alta de boutiques (/empezar): por ahora en la web publicada, con el plan y
/// el periodo elegidos ya cargados.
Future<void> abrirEmpezar({String? plan, String? periodo}) async {
  final params = {'plan': ?plan, 'periodo': ?periodo};
  final uri = Uri.parse('$webAssetsBaseUrl/empezar').replace(queryParameters: params.isEmpty ? null : params);
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}

/// Logo o foto que puede venir del backend (URL absoluta de Supabase) o de los
/// archivos del frontend ("/img/logo.png"): el de Atelier se usa del asset local.
class ImagenTienda extends StatelessWidget {
  const ImagenTienda(this.url, {super.key, this.fit = BoxFit.contain, this.height, this.width, this.contorno = false});

  final String url;
  final BoxFit fit;
  final double? height;
  final double? width;

  /// Logo oscuro sobre fondo oscuro: contorno blanco de 1px, como el
  /// `drop-shadow` de `.logo-contorno` en la web.
  final bool contorno;

  @override
  Widget build(BuildContext context) {
    Widget imagen(Color? tinte) {
      final Widget base = url == '/img/logo.png'
          ? Image.asset('assets/logo.png', fit: fit, height: height, width: width)
          : CachedNetworkImage(
              imageUrl: resolveImageUrl(url),
              fit: fit,
              height: height,
              width: width,
              errorWidget: (_, _, _) => const SizedBox.shrink(),
            );
      if (tinte == null) return base;
      return ColorFiltered(colorFilter: ColorFilter.mode(tinte, BlendMode.srcIn), child: base);
    }

    if (!contorno) return imagen(null);
    return Stack(
      alignment: Alignment.center,
      children: [
        for (final d in const [Offset(1, 0), Offset(-1, 0), Offset(0, 1), Offset(0, -1)])
          Transform.translate(offset: d, child: imagen(Colors.white)),
        imagen(null),
      ],
    );
  }
}

/// Inicial con el color de la marca, para tiendas sin logo.
class InicialTienda extends StatelessWidget {
  const InicialTienda({super.key, required this.nombre, required this.color, this.size = 18});

  final String nombre;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final inicial = nombre.trim().isEmpty ? '?' : nombre.trim()[0].toUpperCase();
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      child: Text(inicial, style: TextStyle(color: Colors.white, fontSize: size * 0.55, fontWeight: FontWeight.w800)),
    );
  }
}

// ------------------------------------------------------------------ planes

/// Planes de la plataforma: los mismos de `frontend/src/app/data/planes.ts`
/// (si cambian alla, se cambian aca).
class PlanPlataforma {
  const PlanPlataforma({
    required this.id,
    required this.nombre,
    required this.resumen,
    required this.precioMensual,
    required this.maxSucursales,
    this.diasPrueba,
    required this.incluye,
    required this.noIncluye,
  });

  final String id;
  final String nombre;
  final String resumen;
  final int precioMensual;
  final int maxSucursales;
  final int? diasPrueba;
  final List<String> incluye;
  final List<String> noIncluye;

  bool get esPrueba => diasPrueba != null;

  /// Pagando el anio se cobran 10 meses (2 de regalo).
  int precioPorMes(bool anual) => esPrueba || !anual ? precioMensual : (precioMensual * mesesCobradosAlAnio / 12).round();

  int get precioAnual => precioMensual * mesesCobradosAlAnio;
}

const mesesCobradosAlAnio = 10;
const _offline = 'Operación offline (vende sin internet)';
const _funcionesBase = ['Gestión de productos', 'Gestión de ventas', 'Reservas', _offline, 'Reportes convencionales'];

final planesPlataforma = [
  PlanPlataforma(
    id: 'prueba',
    nombre: 'Prueba',
    resumen: 'Conocé Arlani gratis antes de elegir un plan.',
    precioMensual: 0,
    maxSucursales: 1,
    diasPrueba: 14,
    incluye: ['1 sucursal activa', ..._funcionesBase.where((f) => f != _offline)],
    noIncluye: const [_offline, 'Reportes generativos con IA'],
  ),
  const PlanPlataforma(
    id: 'basico',
    nombre: 'Básico',
    resumen: 'Para la boutique que vende en línea y en mostrador.',
    precioMensual: 199,
    maxSucursales: 2,
    incluye: ['Hasta 2 sucursales activas', ..._funcionesBase],
    noIncluye: ['Reportes generativos con IA'],
  ),
  const PlanPlataforma(
    id: 'profesional',
    nombre: 'Profesional',
    resumen: 'Para cadenas con varias sucursales que quieren crecer con IA.',
    precioMensual: 499,
    maxSucursales: 10,
    incluye: ['Hasta 10 sucursales activas', ..._funcionesBase, 'Reportes generativos con IA'],
    noIncluye: [],
  ),
];

final maxSucursalesPlataforma = planesPlataforma.map((p) => p.maxSucursales).reduce((a, b) => a > b ? a : b);

/// El plan pago mas chico que alcanza para esa cantidad de sucursales (la
/// prueba no se recomienda: es temporal).
PlanPlataforma planParaSucursales(int cantidad) {
  final pagos = planesPlataforma.where((p) => !p.esPrueba).toList();
  return pagos.firstWhere((p) => cantidad <= p.maxSucursales, orElse: () => pagos.last);
}

// ------------------------------------------------------------ menu del encabezado

/// Secciones de la portada a las que llevan los enlaces del menu.
enum SeccionPortada { inicio, boutiques, promociones, funciones, porQue, precios }

class ItemMenuPlataforma {
  const ItemMenuPlataforma(this.titulo, this.seccion);

  final String titulo;
  final SeccionPortada seccion;
}

const menuPorQue = [
  ItemMenuPlataforma('Boutiques que recién empiezan', SeccionPortada.porQue),
  ItemMenuPlataforma('Cadenas con varias sucursales', SeccionPortada.porQue),
  ItemMenuPlataforma('Tiendas con mala señal', SeccionPortada.porQue),
];

const menuFunciones = [
  ItemMenuPlataforma('Tienda online', SeccionPortada.funciones),
  ItemMenuPlataforma('Ventas en línea y en mostrador', SeccionPortada.funciones),
  ItemMenuPlataforma('Reservas', SeccionPortada.funciones),
  ItemMenuPlataforma('Inventario por sucursal', SeccionPortada.funciones),
  ItemMenuPlataforma('Ventas sin internet', SeccionPortada.funciones),
  ItemMenuPlataforma('Empleados y permisos', SeccionPortada.funciones),
  ItemMenuPlataforma('Reportes con IA', SeccionPortada.funciones),
  ItemMenuPlataforma('Probador virtual', SeccionPortada.funciones),
  ItemMenuPlataforma('Recomendaciones', SeccionPortada.funciones),
];
