import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/auth_provider.dart';
import '../../models/producto_publico.dart';
import '../../models/sucursal.dart';
import '../../models/temporada.dart';
import 'catalogo_repository.dart';

final catalogoRepositoryProvider = Provider<CatalogoRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return CatalogoRepository(apiClient.dio);
});

/// Se cargan una sola vez y quedan cacheados (equivalente a `CatalogoPublico`
/// / `load()` con bandera `_cargado` en Angular): Riverpod ya cachea el
/// resultado de un FutureProvider hasta que se invalide.
final productosPublicosProvider = FutureProvider<List<ProductoPublico>>((ref) {
  return ref.watch(catalogoRepositoryProvider).listProductos();
});

final sucursalesPublicasProvider = FutureProvider<List<SucursalPublica>>((ref) {
  return ref.watch(catalogoRepositoryProvider).listSucursales();
});

final temporadasPublicasProvider = FutureProvider<List<Temporada>>((ref) {
  return ref.watch(catalogoRepositoryProvider).listTemporadas();
});

/// Sucursales y temporadas de una boutique (null = las de todas), para los
/// filtros del catalogo universal.
final sucursalesDeTiendaProvider = FutureProvider.family<List<SucursalPublica>, String?>((ref, tienda) {
  return ref.watch(catalogoRepositoryProvider).listSucursales(tienda: tienda);
});

final temporadasDeTiendaProvider = FutureProvider.family<List<Temporada>, String?>((ref, tienda) {
  return ref.watch(catalogoRepositoryProvider).listTemporadas(tienda: tienda);
});

/// Para quien es una prenda (`data/publicos.ts`).
const publicos = [
  ('mujer', 'Mujer'),
  ('hombre', 'Hombre'),
  ('unisex', 'Unisex'),
  ('nina', 'Niña'),
  ('nino', 'Niño'),
  ('bebe', 'Bebé'),
];

/// Una prenda unisex tambien aparece al filtrar Mujer u Hombre.
bool coincidePublico(String? prenda, String? filtro) {
  if (filtro == null) return true;
  return prenda == filtro || (prenda == 'unisex' && (filtro == 'mujer' || filtro == 'hombre'));
}

/// Categorias reales derivadas de los productos cargados (no una lista fija).
final categoriasDisponiblesProvider = Provider<List<String>>((ref) {
  final productos = ref.watch(productosPublicosProvider).valueOrNull ?? [];
  final vistas = <String>{};
  for (final p in productos) {
    vistas.add(p.categoriaNombre);
  }
  final lista = vistas.toList()..sort();
  return lista;
});

/// Marcas reales derivadas de los productos cargados.
final marcasDisponiblesProvider = Provider<List<String>>((ref) {
  final productos = ref.watch(productosPublicosProvider).valueOrNull ?? [];
  final vistas = <String>{};
  for (final p in productos) {
    vistas.add(p.marcaNombre);
  }
  final lista = vistas.toList()..sort();
  return lista;
});

/// Filtros de la tienda, compartidos entre la pantalla de filtros y la
/// grilla — equivalente a `TiendaFiltros` en Angular.
class TiendaFiltrosState {
  const TiendaFiltrosState({
    this.busqueda = '',
    this.categoria,
    this.marcas = const {},
    this.sucursal,
    this.temporada,
    this.precioMin,
    this.precioMax,
    this.tienda,
    this.publico,
  });

  final String busqueda;

  /// Catalogo universal: subdominio de la boutique elegida (null = todas).
  final String? tienda;

  /// Para quien: mujer, hombre, nina, nino o bebe (null = todos).
  final String? publico;

  final String? categoria;
  final Set<String> marcas;
  final String? sucursal;
  final String? temporada;
  final double? precioMin;
  final double? precioMax;

  TiendaFiltrosState copyWith({
    String? busqueda,
    String? categoria,
    bool clearCategoria = false,
    Set<String>? marcas,
    String? sucursal,
    bool clearSucursal = false,
    String? temporada,
    bool clearTemporada = false,
    double? precioMin,
    bool clearPrecioMin = false,
    double? precioMax,
    bool clearPrecioMax = false,
    String? tienda,
    bool clearTienda = false,
    String? publico,
    bool clearPublico = false,
  }) {
    return TiendaFiltrosState(
      busqueda: busqueda ?? this.busqueda,
      categoria: clearCategoria ? null : (categoria ?? this.categoria),
      marcas: marcas ?? this.marcas,
      sucursal: clearSucursal ? null : (sucursal ?? this.sucursal),
      temporada: clearTemporada ? null : (temporada ?? this.temporada),
      precioMin: clearPrecioMin ? null : (precioMin ?? this.precioMin),
      precioMax: clearPrecioMax ? null : (precioMax ?? this.precioMax),
      tienda: clearTienda ? null : (tienda ?? this.tienda),
      publico: clearPublico ? null : (publico ?? this.publico),
    );
  }
}

class TiendaFiltrosNotifier extends StateNotifier<TiendaFiltrosState> {
  TiendaFiltrosNotifier() : super(const TiendaFiltrosState());

  void setBusqueda(String value) => state = state.copyWith(busqueda: value);

  void setCategoria(String? categoria) {
    state = categoria == null ? state.copyWith(clearCategoria: true) : state.copyWith(categoria: categoria);
  }

  void toggleMarca(String marca) {
    final next = {...state.marcas};
    next.contains(marca) ? next.remove(marca) : next.add(marca);
    state = state.copyWith(marcas: next);
  }

  void limpiarMarcas() => state = state.copyWith(marcas: {});

  void setSucursal(String? sucursal) {
    state = sucursal == null ? state.copyWith(clearSucursal: true) : state.copyWith(sucursal: sucursal);
  }

  void setTemporada(String? temporada) {
    state = temporada == null ? state.copyWith(clearTemporada: true) : state.copyWith(temporada: temporada);
  }

  void setPrecio(double? min, double? max) {
    state = state.copyWith(
      precioMin: min,
      clearPrecioMin: min == null,
      precioMax: max,
      clearPrecioMax: max == null,
    );
  }

  /// Al cambiar de boutique, la sucursal y la temporada elegidas pueden no ser
  /// suyas: se limpian (igual que `seleccionarTienda` en tienda-filtros.ts).
  void setTienda(String? tienda) {
    state = state.copyWith(tienda: tienda, clearTienda: tienda == null, clearSucursal: true, clearTemporada: true);
  }

  void setPublico(String? publico) {
    state = publico == null ? state.copyWith(clearPublico: true) : state.copyWith(publico: publico);
  }

  void limpiarTodo() => state = const TiendaFiltrosState();
}

final tiendaFiltrosProvider = StateNotifierProvider<TiendaFiltrosNotifier, TiendaFiltrosState>(
  (ref) => TiendaFiltrosNotifier(),
);

/// Lista filtrada final que consume la grilla de la tienda.
final productosFiltradosProvider = Provider<List<ProductoPublico>>((ref) {
  final productos = ref.watch(productosPublicosProvider).valueOrNull ?? [];
  final filtros = ref.watch(tiendaFiltrosProvider);
  final termino = filtros.busqueda.trim().toLowerCase();

  return productos.where((p) {
    final coincideTienda = filtros.tienda == null || p.tienda == filtros.tienda;
    final coincideBusqueda = termino.isEmpty ||
        p.nombre.toLowerCase().contains(termino) ||
        p.marcaNombre.toLowerCase().contains(termino) ||
        p.tiendaNombre.toLowerCase().contains(termino);
    final paraQuien = coincidePublico(p.publico, filtros.publico);
    final coincideCategoria = filtros.categoria == null || p.categoriaNombre == filtros.categoria;
    final coincideMarca = filtros.marcas.isEmpty || filtros.marcas.contains(p.marcaNombre);
    final coincideSucursal = filtros.sucursal == null || p.sucursalesDisponibles.contains(filtros.sucursal);
    final coincideTemporada = filtros.temporada == null || p.temporadaNombre == filtros.temporada;
    final coincidePrecioMin = filtros.precioMin == null || p.precio >= filtros.precioMin!;
    final coincidePrecioMax = filtros.precioMax == null || p.precio <= filtros.precioMax!;
    return coincideTienda &&
        coincideBusqueda &&
        paraQuien &&
        coincideCategoria &&
        coincideMarca &&
        coincideSucursal &&
        coincideTemporada &&
        coincidePrecioMin &&
        coincidePrecioMax;
  }).toList();
});

/// "Novedades": los 4 productos con id mas alto (no hay fecha de alta propia
/// en el catalogo, igual criterio que se uso en la web).
final novedadesProvider = Provider<List<ProductoPublico>>((ref) {
  final productos = List<ProductoPublico>.of(ref.watch(productosPublicosProvider).valueOrNull ?? []);
  productos.sort((a, b) => b.id.compareTo(a.id));
  return productos.take(4).toList();
});

/// "Descuentos": productos con precio_original mayor al precio actual.
final descuentosProvider = Provider<List<ProductoPublico>>((ref) {
  final productos = ref.watch(productosPublicosProvider).valueOrNull ?? [];
  return productos.where((p) => p.tieneDescuento).take(3).toList();
});
