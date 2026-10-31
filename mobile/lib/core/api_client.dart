import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api_config.dart';
import 'secure_storage.dart';

/// Extrae el mensaje de error que devuelve FastAPI (`{"detail": "..."}`,
/// a veces `detail` es una lista de errores de validacion de Pydantic).
String extractErrorMessage(Object error) {
  if (error is DioException) {
    if (error.type == DioExceptionType.connectionError ||
        error.type == DioExceptionType.connectionTimeout) {
      return 'No pudimos conectar con el servidor.';
    }
    final data = error.response?.data;
    if (data is Map && data['detail'] != null) {
      final detail = data['detail'];
      if (detail is String) return detail;
      if (detail is List && detail.isNotEmpty) {
        final first = detail.first;
        if (first is Map && first['msg'] != null) return first['msg'].toString();
      }
    }
  }
  return 'Ocurrio un error inesperado.';
}

final secureStorageProvider = Provider<SecureStorage>((ref) => SecureStorage());

/// Cliente Dio unico para toda la app: adjunta el Bearer token en cada
/// request y, ante un 401, dispara `onUnauthorized` (que el auth_provider
/// conecta a un logout forzado) — equivalente a `auth-interceptor.ts`.
class ApiClient {
  ApiClient({required this.secureStorage, required this.onUnauthorized}) {
    dio = Dio(
      BaseOptions(
        baseUrl: apiBaseUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 15),
        // CU17: le dice al backend de que app vino la accion (bitacora,
        // columna "plataforma") -- equivalente a lo que manda
        // `auth-interceptor.ts` en la web.
        headers: {'X-Client-Platform': 'movil'},
      ),
    );

    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await secureStorage.readToken();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        // Sesion que se renueva sola mientras se usa (igual que la web): el
        // backend manda el token nuevo en X-Token-Renovado.
        onResponse: (response, handler) async {
          final nuevo = response.headers.value('x-token-renovado');
          if (nuevo != null && nuevo.isNotEmpty) await secureStorage.saveToken(nuevo);
          handler.next(response);
        },
        onError: (error, handler) async {
          final hadToken = error.requestOptions.headers.containsKey('Authorization');
          if (error.response?.statusCode == 401 && hadToken) {
            await onUnauthorized(extractErrorMessage(error));
          }
          handler.next(error);
        },
      ),
    );
  }

  final SecureStorage secureStorage;
  final Future<void> Function(String message) onUnauthorized;
  late final Dio dio;
}
