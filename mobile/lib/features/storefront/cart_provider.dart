import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/carrito.dart';
import 'carrito_repository.dart';

/// CU11: el carrito ahora persiste contra el backend (ligado al cliente
/// autenticado), igual que `services/cart.ts` en la web -- reemplaza la
/// version anterior 100% local (shared_preferences). Por eso requiere
/// sesion iniciada; quien lo usa llama `cargar()` cuando corresponde (ver
/// el listener de sesion en `main.dart`), no se auto-carga solo.
class CartState {
  const CartState({this.carrito, this.loading = false, this.error});

  final Carrito? carrito;
  final bool loading;
  final String? error;

  List<DetalleCarrito> get items => carrito?.detalles ?? const [];
  double get total => carrito?.total ?? 0;
  int get totalItems => carrito?.totalItems ?? 0;

  CartState copyWith({Carrito? carrito, bool? loading, String? error, bool clearError = false}) {
    return CartState(
      carrito: carrito ?? this.carrito,
      loading: loading ?? this.loading,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

class CartNotifier extends StateNotifier<CartState> {
  CartNotifier(this._repo) : super(const CartState());

  final CarritoRepository _repo;

  // Sube con cada cambio del carrito. Al iniciar sesion se carga el carrito
  // y, si el cliente agrega su primera prenda mientras esa respuesta viene en
  // camino, la respuesta vieja (sin la prenda) ya no pisa la nueva.
  int _cambios = 0;

  Future<void> cargar() async {
    final inicio = _cambios;
    state = state.copyWith(loading: true, clearError: true);
    try {
      final carrito = await _repo.obtener();
      if (_cambios != inicio) return;
      state = state.copyWith(carrito: carrito, loading: false);
    } catch (_) {
      if (_cambios != inicio) return;
      // Sin sesion (401) u otro error de red: el carrito se ve vacio.
      state = const CartState();
    }
  }

  void _aplicar(Carrito carrito) {
    _cambios++;
    state = state.copyWith(carrito: carrito, loading: false);
  }

  void limpiarLocal() {
    _cambios++;
    state = const CartState();
  }

  Future<void> agregar({
    required int productoId,
    required int tallaId,
    required int colorId,
    required int sucursalId,
    required int cantidad,
  }) async {
    final carrito = await _repo.agregar(
      productoId: productoId,
      tallaId: tallaId,
      colorId: colorId,
      sucursalId: sucursalId,
      cantidad: cantidad,
    );
    _aplicar(carrito);
  }

  Future<void> actualizarCantidad(int detalleId, int cantidad) async {
    if (cantidad < 1) {
      await eliminar(detalleId);
      return;
    }
    final carrito = await _repo.actualizarCantidad(detalleId, cantidad);
    _aplicar(carrito);
  }

  Future<void> eliminar(int detalleId) async {
    final carrito = await _repo.eliminar(detalleId);
    _aplicar(carrito);
  }

  Future<void> vaciar() async {
    final carrito = await _repo.vaciar();
    _aplicar(carrito);
  }
}

final cartProvider = StateNotifierProvider<CartNotifier, CartState>((ref) {
  final repo = ref.watch(carritoRepositoryProvider);
  return CartNotifier(repo);
});

final cartTotalItemsProvider = Provider<int>((ref) => ref.watch(cartProvider).totalItems);

final cartTotalPriceProvider = Provider<double>((ref) => ref.watch(cartProvider).total);
