import 'package:cached_network_image/cached_network_image.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import '../auth/auth_provider.dart';
import '../empezar/panel_paypal.dart';
import '../portada/plataforma_data.dart';
import 'offline_servicio.dart';
import 'offline_widgets.dart';
import 'sin_conexion_cliente_screen.dart';

/// Compra hecha sin conexion, revisada con el precio y el stock de AHORA.
class _Compra {
  _Compra(this.j);
  final Map<String, dynamic> j;

  String get uuid => j['uuid'].toString();
  String get tienda => j['tienda'].toString();
  String? get logo => j['logo_url'] as String?;
  String? get color => j['color_marca'] as String?;
  String get sucursal => j['sucursal'].toString();
  String get entrega => j['entrega'].toString();
  String? get direccion => j['direccion'] as String?;
  String get formaPago => j['forma_pago'].toString();
  String get estado => j['estado'].toString();
  String? get mensaje => j['mensaje'] as String?;
  int? get ventaId => j['venta_id'] as int?;
  DateTime get registradaEn => DateTime.parse(j['registrada_en'].toString());
  List<Map<String, dynamic>> get items => (j['items'] as List).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get metodos => (j['metodos'] as List? ?? []).cast<Map<String, dynamic>>();
  double get totalGuardado => double.parse(j['total_guardado'].toString());
  double get totalActual => double.parse(j['total_actual'].toString());
  String get totalUsd => j['total_usd'].toString();
  bool get precioCambio => j['precio_cambio'] == true;
  bool get sinStock => j['sin_stock'] == true;
  bool get puedePagar => j['puede_pagar'] == true;
}

/// "Compras por pagar" (`pages/pagar-compras` de la web). Si una prenda se
/// agoto no se puede comprar; si cambio el precio se muestra el anterior y el
/// nuevo. PayPal se aprueba en el panel incrustado de esta misma pantalla.
class PagarComprasScreen extends ConsumerStatefulWidget {
  const PagarComprasScreen({super.key});

  @override
  ConsumerState<PagarComprasScreen> createState() => _PagarComprasScreenState();
}

class _PagarComprasScreenState extends ConsumerState<PagarComprasScreen> {
  List<_Compra> _compras = [];
  final List<_Compra> _hechas = [];
  bool _cargando = true;
  String _error = '';
  final Map<String, String> _errorDe = {};
  String? _procesando;
  final Map<String, int> _metodoDe = {};
  final Map<String, XFile> _archivoDe = {};
  // Panel de PayPal abierto: (uuid, order_id, url).
  (String, String, String)? _panel;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = '';
    });
    try {
      final r = await _dio.get('/offline/pedidos');
      _compras = [for (final c in (r.data as List).cast<Map<String, dynamic>>()) _Compra(c)];
    } catch (_) {
      _error = 'No pudimos revisar tus compras: necesitas conexión.';
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _ejecutar(_Compra c, Future<Response> Function() accion) async {
    setState(() {
      _procesando = c.uuid;
      _errorDe.remove(c.uuid);
    });
    try {
      final r = _Compra((await accion()).data as Map<String, dynamic>);
      setState(() {
        _panel = null;
        _compras.removeWhere((x) => x.uuid == c.uuid);
        if (r.estado == 'pagada') _hechas.insert(0, r);
      });
      // El telefono actualiza su copia y el aviso deja de mostrarse.
      ref.read(offlineProvider).sincronizar();
    } catch (e) {
      setState(() => _errorDe[c.uuid] = e is DioException && e.response != null
          ? extractErrorMessage(e)
          : 'No se pudo completar. Revisa tu conexión e intenta de nuevo.');
      // Puede que el precio o el stock hayan cambiado: se revisa de nuevo.
      _cargar();
    } finally {
      if (mounted) setState(() => _procesando = null);
    }
  }

  Future<void> _abrirPaypal(_Compra c) async {
    try {
      final r = await _dio.post('/offline/pedidos/${c.uuid}/paypal/orden', data: {'guardar_paypal': true});
      final url = (r.data as Map)['approve_url'] as String?;
      if (url == null) throw StateError('sin enlace');
      setState(() => _panel = (c.uuid, (r.data as Map)['order_id'].toString(), url));
    } catch (e) {
      setState(() => _errorDe[c.uuid] = 'Ocurrió un error con PayPal. Intenta de nuevo o elige otro método.');
    }
  }

  @override
  Widget build(BuildContext context) {
    return MarcoClienteOffline(
      volver: 'Sin conexión',
      alVolver: () => context.canPop() ? context.pop() : context.go('/sin-conexion'),
      children: [
        const CabeceraOffline(
          titulo: 'Compras por pagar',
          texto: 'Las compras que hiciste sin conexión. Revisamos el precio y el stock de ahora: si una prenda se agotó no se '
              'puede comprar; si cambió el precio, te mostramos el anterior y el nuevo antes de pagar.',
        ),
        Align(alignment: Alignment.centerLeft, child: BotonOffline('Revisar de nuevo', onPressed: _cargando ? null : _cargar)),
        const SizedBox(height: 14),
        if (_error.isNotEmpty) AvisoOffline(_error, error: true),
        for (final h in _hechas)
          Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(12),
            color: const Color(0xFFEEF0F5),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${h.tienda}: ${h.mensaje ?? 'Compra pagada.'}', style: textoOffline(size: 12.5, color: marcaOffline)),
              if (h.ventaId != null)
                TextButton(onPressed: () => context.push('/mis-compras/${h.ventaId}'), child: const Text('Ver comprobante')),
            ]),
          ),
        if (_cargando)
          const Padding(padding: EdgeInsets.all(30), child: Center(child: CircularProgressIndicator()))
        else ...[
          if (_compras.isEmpty && _hechas.isEmpty) subOffline('No tienes compras sin conexión por pagar.'),
          for (final c in _compras) _tarjeta(c),
        ],
      ],
    );
  }

  Widget _tarjeta(_Compra c) {
    final marca = colorMarca(c.color);
    final metodo = c.metodos.where((m) => m['id'] == _metodoDe[c.uuid]).firstOrNull;
    final ocupado = _procesando == c.uuid;
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: marca, width: 3), left: const BorderSide(color: bordeOffline),
            right: const BorderSide(color: bordeOffline), bottom: const BorderSide(color: bordeOffline)),
      ),
      child: Opacity(
        opacity: c.sinStock ? 0.85 : 1,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              if (c.logo != null) ...[
                SizedBox(width: 40, height: 40, child: CachedNetworkImage(imageUrl: resolveImageUrl(c.logo!), fit: BoxFit.contain)),
                const SizedBox(width: 10),
              ],
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(c.tienda, style: GoogleFonts.playfairDisplay(fontSize: 19, fontWeight: FontWeight.w600, color: marca)),
                  subOffline('Hecha sin conexión el ${fechaCorta(c.registradaEn)} · '
                      '${c.entrega == 'envio' ? 'Envío a ${c.direccion ?? 'tu dirección'}' : 'Retiro en ${c.sucursal}'} · '
                      '${c.formaPago == 'contra_entrega' ? 'Pago contra entrega' : 'Pago en línea'}'),
                ]),
              ),
            ]),
            const SizedBox(height: 10),
            if (c.estado == 'en_espera')
              const AvisoOffline(
                'En espera de stock: estás en la cola de estas prendas. Tu compra se completa sola apenas vuelva a haber '
                'stock de todas (hasta 7 días desde que la hiciste); si sube el precio te preguntamos antes. Puedes '
                'cancelarla cuando quieras.',
              )
            else if (c.sinStock)
              const AvisoOffline('Ya no hay stock suficiente de alguna prenda: no se puede comprar. Puedes cancelarla y elegir otra cosa.',
                  error: true)
            else if (c.precioCambio)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(12),
                color: const Color(0xFFFFF4E0),
                child: Text(
                  'El precio cambió desde que la armaste: antes Bs ${bs(c.totalGuardado)}, ahora Bs ${bs(c.totalActual)}. '
                  'Si pagas, es con el precio de ahora.',
                  style: textoOffline(size: 12.5, color: const Color(0xFF8A4F00)),
                ),
              ),
            for (final i in c.items) _linea(i),
            const SizedBox(height: 10),
            Text('Total: Bs ${bs(c.totalActual)}', style: textoOffline(size: 15, peso: FontWeight.w800, color: marcaOffline)),
            if (c.puedePagar) ...[
              const SizedBox(height: 10),
              if (c.formaPago == 'contra_entrega') ...[
                subOffline('Al confirmar, la tienda aparta tus prendas. Pagas Bs ${bs(c.totalActual)} en efectivo '
                    '${c.entrega == 'envio' ? 'al recibirla' : 'al recogerla en ${c.sucursal}'}.'),
                const SizedBox(height: 10),
                BotonOffline(ocupado ? 'Confirmando…' : 'Confirmar compra',
                    ancho: true,
                    onPressed: ocupado ? null : () => _ejecutar(c, () => _dio.post('/offline/pedidos/${c.uuid}/contra-entrega'))),
              ] else ...[
                etiquetaOffline('Elige cómo pagar'),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  for (final m in c.metodos)
                    OpcionOffline(
                      texto: m['nombre'].toString(),
                      activa: m['id'] == _metodoDe[c.uuid],
                      onTap: () {
                        setState(() {
                          _metodoDe[c.uuid] = m['id'] as int;
                          _errorDe.remove(c.uuid);
                          _panel = null;
                        });
                        if (m['tipo'] == 'paypal') _abrirPaypal(c);
                      },
                    ),
                ]),
                if (metodo != null && metodo['tipo'] == 'paypal') ...[
                  subOffline('Cobro en dólares al cambio oficial: US\$ ${c.totalUsd}'),
                  const SizedBox(height: 8),
                  if (_panel case (final uuid, final orderId, final url) when uuid == c.uuid)
                    PanelPaypal(
                      key: ValueKey(orderId),
                      url: url,
                      orderId: orderId,
                      alTerminar: (id) {
                        if (id == null) {
                          setState(() {
                            _panel = null;
                            _errorDe[c.uuid] = 'Cancelaste el pago. Puedes intentarlo de nuevo.';
                          });
                          return;
                        }
                        _ejecutar(c, () => _dio.post('/offline/pedidos/${c.uuid}/paypal/capturar/$id'))
                            // La cuenta quedo autorizada: el catalogo sin conexion lo sabe ya.
                            .then((_) => ref.read(offlineProvider).revisarCatalogo(forzar: true).catchError((_) {}));
                      },
                    )
                  else if (ocupado || _errorDe[c.uuid] == null)
                    const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator())),
                ] else if (metodo != null) ...[
                  if (metodo['qr_url'] != null) ...[
                    const SizedBox(height: 8),
                    SizedBox(height: 200, child: CachedNetworkImage(imageUrl: resolveImageUrl(metodo['qr_url'].toString()))),
                  ],
                  if (metodo['banco'] != null || metodo['numero_cuenta'] != null)
                    subOffline('${metodo['banco'] ?? ''} · ${metodo['numero_cuenta'] ?? ''} · ${metodo['titular'] ?? ''}'),
                  if (metodo['instrucciones'] != null) subOffline(metodo['instrucciones'].toString()),
                  etiquetaOffline('Foto del comprobante'),
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder(), foregroundColor: marcaOffline),
                    icon: const Icon(Icons.photo_library_outlined, size: 18),
                    label: Text(_archivoDe[c.uuid]?.name ?? 'Elegir foto'),
                    onPressed: () async {
                      final f = await ImagePicker().pickImage(source: ImageSource.gallery, imageQuality: 85);
                      if (f != null) setState(() => _archivoDe[c.uuid] = f);
                    },
                  ),
                  const SizedBox(height: 10),
                  BotonOffline(
                    ocupado ? 'Enviando…' : 'Enviar comprobante · Bs ${bs(c.totalActual)}',
                    ancho: true,
                    onPressed: ocupado
                        ? null
                        : () {
                            final f = _archivoDe[c.uuid];
                            if (f == null) {
                              setState(() => _errorDe[c.uuid] = 'Sube la foto de tu comprobante de pago.');
                              return;
                            }
                            _ejecutar(c, () async => _dio.post('/offline/pedidos/${c.uuid}/comprobante',
                                data: FormData.fromMap({
                                  'metodo_pago_id': metodo['id'].toString(),
                                  'file': await MultipartFile.fromFile(f.path, filename: f.name),
                                })));
                          },
                  ),
                ],
              ],
            ],
            if (_errorDe[c.uuid] != null) ...[const SizedBox(height: 10), AvisoOffline(_errorDe[c.uuid]!, error: true)],
            TextButton(
              style: TextButton.styleFrom(foregroundColor: const Color(0xFFB3261E)),
              onPressed: ocupado
                  ? null
                  : () async {
                      final si = await showDialog<bool>(
                        context: context,
                        builder: (ctx) => AlertDialog(
                          content: Text('¿Cancelar la compra en ${c.tienda}?'),
                          actions: [
                            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('No')),
                            TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Sí, cancelar')),
                          ],
                        ),
                      );
                      if (si == true) _ejecutar(c, () => _dio.post('/offline/pedidos/${c.uuid}/cancelar'));
                    },
              child: const Text('Cancelar esta compra'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _linea(Map<String, dynamic> i) {
    final guardado = double.parse(i['precio_guardado'].toString());
    final actual = double.parse(i['precio_actual'].toString());
    final stock = i['stock'] as int;
    final cantidad = i['cantidad'] as int;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE)))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('$cantidad× ${i['producto']}', style: textoOffline(size: 13, peso: FontWeight.w600)),
              subOffline('${i['talla']} · ${i['color']}'),
              Text.rich(TextSpan(children: [
                if (guardado != actual)
                  TextSpan(text: 'Bs ${bs(guardado)}  ', style: const TextStyle(decoration: TextDecoration.lineThrough, color: Color(0xFF999999))),
                TextSpan(text: 'Bs ${bs(actual)}'),
              ]), style: textoOffline(size: 12.5)),
            ]),
          ),
          ChipEstado(stock >= cantidad ? 'confirmada' : 'sin_stock',
              texto: stock >= cantidad ? 'Disponible' : (stock == 0 ? 'Agotada' : 'Quedan $stock')),
        ],
      ),
    );
  }
}
