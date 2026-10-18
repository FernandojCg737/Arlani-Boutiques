import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/secure_storage.dart';
import '../../models/usuario.dart';
import 'auth_repository.dart';
import 'google_auth.dart';

class AuthState {
  const AuthState({this.usuario, this.bootstrapping = true, this.sessionMessage});

  final Usuario? usuario;
  final bool bootstrapping;
  final String? sessionMessage;

  bool get isAuthenticated => usuario != null;
  bool get isStaff => usuario?.isStaff ?? false;
  bool get isAdministrador => usuario?.isAdministrador ?? false;

  bool hasPermiso(String codigo) => usuario?.hasPermiso(codigo) ?? false;

  /// Acciones de cliente (carrito, reservar, probador AR): un visitante sin
  /// sesion SI las ve -- al usarlas se le pide iniciar sesion (ver
  /// `asegurarSesion`). Con sesion, solo si su rol tiene ese CU (CU02).
  bool mostrarAccionCliente(String codigo) => !isAuthenticated || hasPermiso(codigo);

  AuthState copyWith({Usuario? usuario, bool clearUsuario = false, bool? bootstrapping, String? sessionMessage, bool clearMessage = false}) {
    return AuthState(
      usuario: clearUsuario ? null : (usuario ?? this.usuario),
      bootstrapping: bootstrapping ?? this.bootstrapping,
      sessionMessage: clearMessage ? null : (sessionMessage ?? this.sessionMessage),
    );
  }
}

/// Equivalente al servicio `Auth` (signals) de Angular: guarda el usuario
/// actual, persiste sesion, y expone login/registro/logout/forceLogout.
class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier(this._repository, this._storage) : super(const AuthState()) {
    _bootstrap();
  }

  final AuthRepository _repository;
  final SecureStorage _storage;

  Future<void> _bootstrap() async {
    final token = await _storage.readToken();
    if (token == null) {
      state = state.copyWith(bootstrapping: false);
      return;
    }
    try {
      final usuario = await _repository.me();
      state = state.copyWith(usuario: usuario, bootstrapping: false);
    } catch (_) {
      await _storage.clear();
      state = state.copyWith(bootstrapping: false, clearUsuario: true);
    }
  }

  Future<void> _persist(TokenResponse token) async {
    await _storage.saveToken(token.accessToken);
    await _storage.saveUsuario(token.usuario.toJson());
    state = state.copyWith(usuario: token.usuario, clearMessage: true);
  }

  Future<void> register({required String nombre, required String email, required String password, String? telefono}) async {
    final token = await _repository.register(nombre: nombre, email: email, password: password, telefono: telefono);
    await _persist(token);
  }

  Future<void> login({required String email, required String password}) async {
    final token = await _repository.login(email: email, password: password);
    await _persist(token);
  }

  Future<void> loginWithGoogle(String credential) async {
    final token = await _repository.loginWithGoogle(credential);
    await _persist(token);
  }

  Future<void> forgotPassword(String email) => _repository.forgotPassword(email);

  Future<String> verifyResetCode({required String email, required String code}) =>
      _repository.verifyResetCode(email: email, code: code);

  Future<void> resetPassword({required String resetToken, required String newPassword}) async {
    final token = await _repository.resetPassword(resetToken: resetToken, newPassword: newPassword);
    await _persist(token);
  }

  Future<void> loginWithResetCode(String resetToken) async {
    final token = await _repository.loginWithResetCode(resetToken);
    await _persist(token);
  }

  Future<void> updateProfile({required String nombre, String? telefono, String? direccion}) async {
    final usuario = await _repository.updateProfile(nombre: nombre, telefono: telefono, direccion: direccion);
    await _storage.saveUsuario(usuario.toJson());
    state = state.copyWith(usuario: usuario);
  }

  Future<void> changePassword({required String actual, required String nueva}) async {
    final token = await _repository.changePassword(actual: actual, nueva: nueva);
    await _persist(token);
  }

  Future<void> logout() async {
    try {
      await _repository.logout();
    } catch (_) {
      // Si ya no hay conexion o el token vencio, igual limpiamos localmente.
    }
    await signOutGoogleSilently();
    await _storage.clear();
    state = state.copyWith(clearUsuario: true, clearMessage: true);
  }

  /// Llamado por el interceptor de Dio ante un 401: la sesion ya no es
  /// valida en el backend (token vencido o reemplazado por otro login).
  Future<void> forceLogout(String message) async {
    await _storage.clear();
    state = state.copyWith(clearUsuario: true, sessionMessage: message);
  }

  void dismissSessionMessage() {
    state = state.copyWith(clearMessage: true);
  }
}

/// Puente para romper el ciclo apiClientProvider -> authProvider ->
/// authRepositoryProvider -> apiClientProvider: el interceptor de Dio solo
/// escribe aca ante un 401, y `authProvider` lo escucha por separado
/// (ver `main.dart`) para disparar el logout forzado.
final unauthorizedEventProvider = StateProvider<String?>((ref) => null);

final apiClientProvider = Provider<ApiClient>((ref) {
  final storage = ref.watch(secureStorageProvider);
  return ApiClient(
    secureStorage: storage,
    onUnauthorized: (message) async {
      ref.read(unauthorizedEventProvider.notifier).state = message;
    },
  );
});

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return AuthRepository(apiClient.dio);
});

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final repo = ref.watch(authRepositoryProvider);
  final storage = ref.watch(secureStorageProvider);
  return AuthNotifier(repo, storage);
});
