import 'package:dio/dio.dart';

import '../../models/usuario.dart';

/// Llama exactamente los mismos endpoints que `auth.ts` / `perfil.ts` en la
/// web, con los mismos nombres de campo que esperan los schemas de FastAPI.
class AuthRepository {
  AuthRepository(this._dio);

  final Dio _dio;

  Future<TokenResponse> register({
    required String nombre,
    required String email,
    required String password,
    String? telefono,
  }) async {
    final res = await _dio.post(
      '/auth/register',
      data: {'nombre': nombre, 'email': email, 'password': password, 'telefono': telefono},
    );
    return TokenResponse.fromJson(res.data as Map<String, dynamic>);
  }

  Future<TokenResponse> login({required String email, required String password}) async {
    final res = await _dio.post('/auth/login', data: {'email': email, 'password': password});
    return TokenResponse.fromJson(res.data as Map<String, dynamic>);
  }

  Future<TokenResponse> loginWithGoogle(String credential) async {
    final res = await _dio.post('/auth/google', data: {'credential': credential});
    return TokenResponse.fromJson(res.data as Map<String, dynamic>);
  }

  Future<Usuario> me() async {
    final res = await _dio.get('/auth/me');
    return Usuario.fromJson(res.data as Map<String, dynamic>);
  }

  Future<void> logout() => _dio.post('/auth/logout');

  Future<void> forgotPassword(String email) => _dio.post('/auth/forgot-password', data: {'email': email});

  Future<String> verifyResetCode({required String email, required String code}) async {
    final res = await _dio.post('/auth/verify-reset-code', data: {'email': email, 'code': code});
    return (res.data as Map<String, dynamic>)['reset_token'] as String;
  }

  Future<TokenResponse> resetPassword({required String resetToken, required String newPassword}) async {
    final res = await _dio.post(
      '/auth/reset-password',
      data: {'reset_token': resetToken, 'new_password': newPassword},
    );
    return TokenResponse.fromJson(res.data as Map<String, dynamic>);
  }

  Future<TokenResponse> loginWithResetCode(String resetToken) async {
    final res = await _dio.post('/auth/login-with-reset-code', data: {'reset_token': resetToken});
    return TokenResponse.fromJson(res.data as Map<String, dynamic>);
  }

  Future<Usuario> updateProfile({required String nombre, String? apellidos, String? telefono, String? direccion}) async {
    final res = await _dio.put(
      '/perfil',
      data: {'nombre': nombre, 'apellidos': apellidos, 'telefono': telefono, 'direccion': direccion},
    );
    return Usuario.fromJson(res.data as Map<String, dynamic>);
  }

  /// CU15: sube (o quita) la foto de perfil.
  Future<Usuario> subirFoto(String ruta, String nombreArchivo) async {
    final res = await _dio.post(
      '/perfil/foto',
      data: FormData.fromMap({'file': await MultipartFile.fromFile(ruta, filename: nombreArchivo)}),
    );
    return Usuario.fromJson(res.data as Map<String, dynamic>);
  }

  Future<Usuario> quitarFoto() async {
    final res = await _dio.delete('/perfil/foto');
    return Usuario.fromJson(res.data as Map<String, dynamic>);
  }

  Future<TokenResponse> changePassword({required String actual, required String nueva}) async {
    final res = await _dio.post(
      '/perfil/cambiar-password',
      data: {'password_actual': actual, 'password_nueva': nueva},
    );
    return TokenResponse.fromJson(res.data as Map<String, dynamic>);
  }
}
