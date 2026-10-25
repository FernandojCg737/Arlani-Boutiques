import 'package:dio/dio.dart';

import '../../models/producto_publico.dart';
import '../../models/sucursal.dart';
import '../../models/temporada.dart';

class CatalogoRepository {
  CatalogoRepository(this._dio);

  final Dio _dio;

  Future<List<ProductoPublico>> listProductos() async {
    final res = await _dio.get('/productos/publico');
    return (res.data as List<dynamic>)
        .map((e) => ProductoPublico.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ProductoPublico> getProducto(int id) async {
    final res = await _dio.get('/productos/publico/$id');
    return ProductoPublico.fromJson(res.data as Map<String, dynamic>);
  }

  Future<List<SucursalPublica>> listSucursales({String? tienda}) async {
    final res = await _dio.get('/sucursales/publico', queryParameters: tienda == null ? null : {'tienda': tienda});
    return (res.data as List<dynamic>)
        .map((e) => SucursalPublica.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<Temporada>> listTemporadas({String? tienda}) async {
    final res = await _dio.get('/temporadas/publico', queryParameters: tienda == null ? null : {'tienda': tienda});
    return (res.data as List<dynamic>).map((e) => Temporada.fromJson(e as Map<String, dynamic>)).toList();
  }
}
