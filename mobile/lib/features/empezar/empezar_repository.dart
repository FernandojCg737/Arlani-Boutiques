import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_config.dart';
import '../auth/auth_provider.dart';

/// Lo que se pide para dar de alta una boutique (igual que
/// `SolicitudSuscripcion` en `services/registro-empresa.ts`).
class SolicitudSuscripcion {
  const SolicitudSuscripcion({
    required this.plan,
    required this.periodo,
    required this.nombre,
    required this.subdominio,
    required this.ciudad,
    required this.sucursales,
    required this.publicos,
    required this.color,
    required this.adminNombre,
    required this.adminEmail,
  });

  final String plan;
  final String periodo;
  final String nombre;
  final String subdominio;
  final String ciudad;
  final int sucursales;
  final List<String> publicos;
  final String color;
  final String adminNombre;
  final String adminEmail;

  Map<String, dynamic> toJson() => {
        'plan': plan,
        'periodo': periodo,
        'boutique': {
          'nombre': nombre,
          'subdominio': subdominio,
          'ciudad': ciudad,
          'sucursales': sucursales,
          'publicos': publicos,
          'color': color,
        },
        'administrador': {'nombre': adminNombre, 'email': adminEmail},
      };
}

class Cotizacion {
  Cotizacion.fromJson(Map<String, dynamic> j)
      : planNombre = j['plan_nombre'] as String,
        montoBob = '${j['monto_bob']}',
        montoUsd = '${j['monto_usd']}',
        tipoCambio = '${j['tipo_cambio']}',
        requierePago = j['requiere_pago'] as bool,
        subdominio = j['subdominio'] as String;

  final String planNombre;
  final String montoBob;
  final String montoUsd;
  final String tipoCambio;
  final bool requierePago;
  final String subdominio;
}

class SuscripcionCreada {
  SuscripcionCreada.fromJson(Map<String, dynamic> j)
      : empresaNombre = j['empresa_nombre'] as String,
        subdominio = j['subdominio'] as String,
        planNombre = j['plan_nombre'] as String,
        adminEmail = j['admin_email'] as String,
        correoDestino = j['correo_destino'] as String,
        metodo = j['metodo'] as String,
        montoBob = '${j['monto_bob']}',
        montoUsd = '${j['monto_usd']}',
        logoGuardado = j['logo_guardado'] as bool,
        correoEnviado = j['correo_enviado'] as bool;

  final String empresaNombre;
  final String subdominio;
  final String planNombre;
  final String adminEmail;
  final String correoDestino;
  final String metodo;
  final String montoBob;
  final String montoUsd;
  final bool logoGuardado;
  final bool correoEnviado;
}

/// Alta de una boutique (`/empresas/...`, los mismos endpoints que la web):
/// se cotiza y valida antes de cobrar, se paga con PayPal y recien ahi el
/// backend crea la empresa, su suscripcion y su Administrador.
class EmpezarRepository {
  EmpezarRepository(this._dio);

  final Dio _dio;

  /// Enlace que quedara para la tienda (si ya lo usa otra, con un numero).
  Future<String> enlaceDisponible(String texto) async {
    final res = await _dio.get('/empresas/enlace-disponible', queryParameters: {'texto': texto});
    return (res.data as Map<String, dynamic>)['subdominio'] as String;
  }

  Future<Cotizacion> cotizar(SolicitudSuscripcion s) async {
    final res = await _dio.post('/empresas/registro/cotizar', data: s.toJson());
    return Cotizacion.fromJson(res.data as Map<String, dynamic>);
  }

  /// Orden de PayPal: (order_id, enlace para aprobarla dentro de la app).
  Future<(String, String?)> crearOrden(SolicitudSuscripcion s) async {
    final res = await _dio.post('/empresas/registro/orden', data: s.toJson());
    final j = res.data as Map<String, dynamic>;
    return (j['order_id'] as String, j['approve_url'] as String?);
  }

  /// orderId: la orden ya aprobada (null en la prueba). logo: data URL.
  Future<SuscripcionCreada> confirmar(SolicitudSuscripcion s, String? orderId, String? logo) async {
    final res = await _dio.post(
      '/empresas/registro/confirmar',
      data: {...s.toJson(), 'order_id': orderId, 'logo': logo},
      // Los enlaces del correo de credenciales apuntan a la web de Arlani.
      options: Options(headers: {'Origin': webAssetsBaseUrl}),
    );
    return SuscripcionCreada.fromJson(res.data as Map<String, dynamic>);
  }
}

final empezarRepositoryProvider = Provider<EmpezarRepository>((ref) {
  return EmpezarRepository(ref.watch(apiClientProvider).dio);
});
