import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import '../empezar/panel_paypal.dart';
import '../portada/plataforma_data.dart' show colorMarca;
import 'cuenta_repository.dart';
import 'estilo_cuenta.dart';

const _estado = {
  'solicitado': 'Por revisar',
  'por_pagar': 'Espera el pago de la diferencia',
  'verificando': 'Comprobante por revisar',
  'completado': 'Completado',
  'rechazado': 'Rechazado',
  'cancelado': 'Cancelado por el cliente',
};

TonoEstado _tono(String estado) => switch (estado) {
      'completado' => TonoEstado.ok,
      'rechazado' => TonoEstado.mal,
      'cancelado' => TonoEstado.neutro,
      _ => TonoEstado.espera,
    };

/// "Mis cambios" (componente `mis-cambios` de la web): los cambios de prenda
/// que pidio el cliente, su estado, cancelarlos y pagar la diferencia si la
/// prenda nueva cuesta mas (PayPal en un panel dentro de la app o comprobante).
class MisCambios extends ConsumerStatefulWidget {
  const MisCambios({super.key});

  @override
  ConsumerState<MisCambios> createState() => _MisCambiosState();
}

class _MisCambiosState extends ConsumerState<MisCambios> {
  List<CambioCliente>? _cambios;
  String? _aviso;
  bool _avisoError = false;

  // Pago de la diferencia en curso.
  int? _pagandoId;
  MetodoCobro? _metodo;
  (String, String)? _panel;
  XFile? _archivo;
  bool _procesando = false;
  String? _errorPago;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final c = await ref.read(cuentaRepositoryProvider).cambios();
      if (mounted) setState(() => _cambios = c);
    } catch (_) {
      if (mounted) setState(() => _cambios = []);
    }
  }

  void _reemplazar(CambioCliente nuevo) {
    setState(() => _cambios = [for (final c in _cambios ?? <CambioCliente>[]) c.id == nuevo.id ? nuevo : c]);
  }

  Future<void> _cancelar(CambioCliente c) async {
    if (!await confirmarCuenta(context, '¿Cancelar el cambio #${c.id}?', si: 'Cancelar cambio')) return;
    try {
      _reemplazar(await ref.read(cuentaRepositoryProvider).cancelarCambio(c.id));
    } catch (e) {
      if (mounted) {
        setState(() {
          _avisoError = true;
          _aviso = extractErrorMessage(e);
        });
      }
    }
  }

  Future<void> _elegirMetodo(CambioCliente c, MetodoCobro m) async {
    setState(() {
      _pagandoId = c.id;
      _metodo = m;
      _panel = null;
      _archivo = null;
      _errorPago = null;
    });
    if (m.tipo != 'paypal') return;
    // PayPal: el panel se abre ahi mismo, debajo de los metodos.
    setState(() => _procesando = true);
    try {
      final (orderId, url) = await ref.read(cuentaRepositoryProvider).ordenDiferencia(c.id);
      if (url == null) throw StateError('sin enlace');
      if (mounted) setState(() => _panel = (orderId, url));
    } catch (e) {
      if (mounted) setState(() => _errorPago = 'No se pudo iniciar el pago con PayPal. Inténtalo de nuevo.');
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _alTerminarPaypal(CambioCliente c, String? orderId) async {
    setState(() => _panel = null);
    if (orderId == null) {
      setState(() => _errorPago = 'Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.');
      return;
    }
    setState(() => _procesando = true);
    try {
      final nuevo = await ref.read(cuentaRepositoryProvider).capturarDiferencia(c.id, orderId);
      _reemplazar(nuevo);
      setState(() {
        _pagandoId = null;
        _avisoError = false;
        _aviso = 'Listo: pagaste la diferencia del cambio #${c.id}. Recoge tu prenda en ${nuevo.sucursalNombre}.';
      });
    } catch (e) {
      if (mounted) setState(() => _errorPago = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _elegirFoto() async {
    final f = await ImagePicker().pickImage(source: ImageSource.gallery, imageQuality: 85);
    if (f == null) return;
    if (await f.length() > 5 * 1024 * 1024) {
      setState(() => _errorPago = 'La foto pesa más de 5 MB. Elige una más liviana.');
      return;
    }
    setState(() {
      _archivo = f;
      _errorPago = null;
    });
  }

  Future<void> _enviarComprobante(CambioCliente c) async {
    final f = _archivo;
    final m = _metodo;
    if (f == null || m == null) return;
    setState(() {
      _procesando = true;
      _errorPago = null;
    });
    try {
      final nuevo = await ref.read(cuentaRepositoryProvider).comprobanteDiferencia(c.id, m.id, f.path, f.name);
      _reemplazar(nuevo);
      setState(() {
        _pagandoId = null;
        _avisoError = false;
        _aviso = 'Recibimos tu comprobante del cambio #${c.id}. La tienda lo revisa y te avisamos.';
      });
    } catch (e) {
      if (mounted) setState(() => _errorPago = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cambios = _cambios;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_aviso != null) AvisoCuenta(_aviso!, error: _avisoError),
        if (cambios == null)
          cargandoCuenta()
        else if (cambios.isEmpty)
          vacioCuenta('Todavía no pediste cambios. Desde Mis Compras puedes cambiar una prenda hasta 24 horas después de comprarla.')
        else
          for (final c in cambios) ...[_tarjeta(c), const SizedBox(height: 12)],
      ],
    );
  }

  Widget _tarjeta(CambioCliente c) {
    final estilo = GoogleFonts.inter(fontSize: 12.5, color: grisOscuroCuenta, height: 1.4);
    return TarjetaCuenta(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text('Cambio #${c.id} · ${c.tiendaNombre}',
                    style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: tintaCuenta)),
              ),
              const SizedBox(width: 8),
              Flexible(child: InsigniaEstado(texto: _estado[c.estado] ?? c.estado, tono: _tono(c.estado))),
            ],
          ),
          const SizedBox(height: 4),
          Text('Compra #${c.ventaId} · ${fechaLarga(c.fechaSolicitud)} · Recoges en ${c.sucursalNombre}',
              style: GoogleFonts.inter(fontSize: 12, height: 1.4, color: grisCuenta)),
          const SizedBox(height: 8),
          Text('${c.cantidad}× ${c.productoOriginal} (${c.tallaOriginal}, ${c.colorOriginal})',
              style: estilo.copyWith(decoration: TextDecoration.lineThrough, color: grisCuenta)),
          Text('→ ${c.cantidad}× ${c.productoNuevo} (${c.tallaNueva}, ${c.colorNuevo})',
              style: estilo.copyWith(fontWeight: FontWeight.w600, color: tintaCuenta)),
          if (c.diferencia > 0) ...[
            const SizedBox(height: 6),
            Text('Diferencia a pagar: Bs ${bs(c.diferencia)}', style: estilo.copyWith(fontWeight: FontWeight.w700, color: ambarCuenta)),
          ] else if (c.diferencia < 0) ...[
            const SizedBox(height: 6),
            Text(
              'Te devuelven Bs ${bs(-c.diferencia)}${c.reembolsoMetodo == 'paypal' ? ' a tu PayPal' : c.reembolsoMetodo == 'en_tienda' ? ' en la tienda' : ''}',
              style: estilo.copyWith(fontWeight: FontWeight.w700, color: verdeCuenta),
            ),
          ],
          if (c.motivoRechazo != null && (c.estado == 'rechazado' || c.estado == 'por_pagar')) ...[
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              color: const Color(0xFFFDECEA),
              child: Text(
                '${c.estado == 'rechazado' ? 'La tienda rechazó el cambio' : 'La tienda no aceptó tu comprobante'}: ${c.motivoRechazo}',
                style: GoogleFonts.inter(fontSize: 12.5, color: rojoCuenta),
              ),
            ),
          ],
          if (c.estado == 'completado') EnlaceCuenta('Ver comprobante', onTap: () => context.push('/mis-cambios/${c.id}')),
          if (c.estado == 'solicitado' || c.estado == 'por_pagar')
            EnlaceCuenta('Cancelar cambio', peligro: true, onTap: _procesando ? null : () => _cancelar(c)),
          if (c.estado == 'por_pagar') _pago(c),
        ],
      ),
    );
  }

  /// `.mc-pago`: metodos de la tienda para pagar la diferencia.
  Widget _pago(CambioCliente c) {
    final activo = _pagandoId == c.id;
    final m = activo ? _metodo : null;
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.only(top: 12),
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: bordeCuenta))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Paga Bs ${bs(c.diferencia)} a ${c.tiendaNombre} para completar tu cambio:',
              style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: tintaCuenta)),
          const SizedBox(height: 10),
          if (c.metodos.isEmpty)
            vacioCuenta('La tienda todavía no configuró cómo cobrar en línea: paga en la sucursal.')
          else
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final metodo in c.metodos)
                  _BotonMetodo(
                    metodo: metodo,
                    activo: activo && _metodo?.id == metodo.id,
                    onTap: _procesando ? null : () => _elegirMetodo(c, metodo),
                  ),
              ],
            ),
          if (activo && _errorPago != null) ...[const SizedBox(height: 12), AvisoCuenta(_errorPago!, error: true)],
          if (activo && _procesando) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: 10),
                Text('Un momento…', style: GoogleFonts.inter(fontSize: 12.5, color: grisOscuroCuenta)),
              ],
            ),
          ],
          if (_panel case (final orderId, final url) when activo && m?.tipo == 'paypal') ...[
            const SizedBox(height: 12),
            Text('Pagas US\$ ${c.diferenciaUsd?.toStringAsFixed(2) ?? ''} (al cambio oficial). Inicia sesión en PayPal y aprueba:',
                style: GoogleFonts.inter(fontSize: 12.5, color: grisOscuroCuenta)),
            const SizedBox(height: 8),
            PanelPaypal(
              url: url,
              orderId: orderId,
              alto: (MediaQuery.sizeOf(context).height * 0.75).clamp(460.0, 680.0),
              alTerminar: (id) => _alTerminarPaypal(c, id),
            ),
          ],
          if (m != null && m.tipo != 'paypal') ...[
            const SizedBox(height: 12),
            if (m.qrUrl != null)
              Center(
                child: CachedNetworkImage(imageUrl: resolveImageUrl(m.qrUrl!), width: 200, height: 200, fit: BoxFit.contain),
              ),
            if (m.banco != null || m.numeroCuenta != null || m.titular != null) ...[
              const SizedBox(height: 8),
              Text(
                [if (m.banco != null) m.banco!, if (m.numeroCuenta != null) 'Cuenta ${m.numeroCuenta}', if (m.titular != null) 'Titular ${m.titular}']
                    .join(' · '),
                style: GoogleFonts.inter(fontSize: 12.5, color: tintaCuenta),
              ),
            ],
            if (m.instrucciones != null) ...[
              const SizedBox(height: 6),
              Text(m.instrucciones!, style: GoogleFonts.inter(fontSize: 12.5, color: grisOscuroCuenta)),
            ],
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _procesando ? null : _elegirFoto,
              icon: const Icon(Icons.photo_outlined, size: 18),
              label: Text(_archivo == null ? 'Elegir foto del comprobante' : _archivo!.name,
                  overflow: TextOverflow.ellipsis, style: GoogleFonts.inter(fontSize: 12.5)),
              style: OutlinedButton.styleFrom(
                foregroundColor: tintaCuenta,
                side: const BorderSide(color: Color(0xFFDDDDDD)),
                shape: const RoundedRectangleBorder(),
                minimumSize: const Size.fromHeight(44),
              ),
            ),
            const SizedBox(height: 10),
            BotonCuenta(
              _procesando ? 'Enviando…' : 'Enviar comprobante',
              ancho: true,
              onTap: _archivo == null || _procesando ? null : () => _enviarComprobante(c),
            ),
          ],
        ],
      ),
    );
  }
}

class _BotonMetodo extends StatelessWidget {
  const _BotonMetodo({required this.metodo, required this.activo, required this.onTap});

  final MetodoCobro metodo;
  final bool activo;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: activo ? tintaCuenta : Colors.white,
          border: Border.all(color: activo ? tintaCuenta : const Color(0xFFDDDDDD)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(metodo.nombre,
                style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: activo ? Colors.white : tintaCuenta)),
            Text(metodo.requiereComprobante ? 'Con comprobante' : 'Se confirma al instante',
                style: GoogleFonts.inter(fontSize: 11, color: activo ? Colors.white70 : grisCuenta)),
          ],
        ),
      ),
    );
  }
}

// ======================================================= pedir un cambio

/// "Cambiar prenda (24h)" desde Mis compras: abre el formulario del cambio
/// con el color de la tienda que vendio ([colorTienda], hex). Devuelve el
/// cambio pedido (o null si se cerro).
Future<CambioCliente?> pedirCambio(BuildContext context, WidgetRef ref, int ventaId, {String? colorTienda}) async {
  final OpcionesCambio opciones;
  try {
    opciones = await ref.read(cuentaRepositoryProvider).opcionesCambio(ventaId);
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(extractErrorMessage(e))));
    }
    return null;
  }
  if (!context.mounted) return null;
  final h = opciones.plazoHasta;
  final marca = colorMarca(colorTienda ?? opciones.tiendaColor);
  return abrirHojaCuenta<CambioCliente>(
    context,
    titulo: 'Cambiar una prenda',
    subtitulo:
        'Compra #${opciones.ventaId} · ${opciones.tiendaNombre} · hasta el ${h.day}/${h.month} ${h.hour.toString().padLeft(2, '0')}:${h.minute.toString().padLeft(2, '0')}',
    cuerpo: (_) => _FormularioCambio(opciones: opciones, marca: marca),
  );
}

class _FormularioCambio extends ConsumerStatefulWidget {
  const _FormularioCambio({required this.opciones, required this.marca});

  final OpcionesCambio opciones;

  /// Color de la tienda dueña de la prenda.
  final Color marca;

  @override
  ConsumerState<_FormularioCambio> createState() => _FormularioCambioState();
}

class _FormularioCambioState extends ConsumerState<_FormularioCambio> {
  int? _lineaId;
  int _cantidad = 1;
  PrendaCambio? _prenda;
  int? _tallaId;
  int? _colorId;
  int? _sucursalId;
  String _motivo = 'talla';
  final _observaciones = TextEditingController();
  bool _enviando = false;
  String? _error;

  OpcionesCambio get o => widget.opciones;
  Color get _marca => widget.marca;
  LineaCambiable? get _linea => o.lineas.where((l) => l.itemLineaId == _lineaId).firstOrNull;
  VarianteCambio? get _variante => _prenda?.variantes.where((v) => v.tallaId == _tallaId && v.colorId == _colorId).firstOrNull;
  StockSucursal? get _sucursal => _variante?.sucursales.where((s) => s.sucursalId == _sucursalId).firstOrNull;

  @override
  void initState() {
    super.initState();
    final libres = o.lineas.where((l) => l.disponibles > 0).toList();
    if (libres.length == 1) _lineaId = libres.first.itemLineaId;
  }

  @override
  void dispose() {
    _observaciones.dispose();
    super.dispose();
  }

  bool _esLaMisma(PrendaCambio p, VarianteCambio v) {
    final l = _linea;
    return l != null && p.nombre == l.productoNombre && v.tallaCodigo == l.tallaCodigo && v.colorNombre == l.colorNombre;
  }

  bool _colorDisponible(PrendaCambio p, VarianteCambio v) => !_esLaMisma(p, v) && v.sucursales.any((s) => s.stock >= _cantidad);

  bool _tallaDisponible(PrendaCambio p, int tallaId) => p.variantes.any((v) => v.tallaId == tallaId && _colorDisponible(p, v));

  void _elegirPrenda(PrendaCambio p) {
    setState(() {
      _prenda = p;
      _tallaId = null;
      _colorId = null;
      _sucursalId = null;
    });
    final tallas = {for (final v in p.variantes) if (_tallaDisponible(p, v.tallaId)) v.tallaId};
    if (tallas.length == 1) _elegirTalla(tallas.first);
  }

  void _elegirTalla(int id) {
    final p = _prenda!;
    final opciones = p.variantes.where((v) => v.tallaId == id && _colorDisponible(p, v)).toList();
    setState(() {
      _tallaId = id;
      _colorId = null;
      _sucursalId = null;
    });
    if (opciones.length == 1) _elegirColor(opciones.first);
  }

  void _elegirColor(VarianteCambio v) {
    final conStock = v.sucursales.where((s) => s.stock >= _cantidad).toList();
    final deLaCompra = conStock.where((s) => s.sucursalId == o.sucursalId).firstOrNull;
    setState(() {
      _colorId = v.colorId;
      _sucursalId = deLaCompra?.sucursalId ?? (conStock.length == 1 ? conStock.first.sucursalId : null);
    });
  }

  bool get _listo {
    final l = _linea;
    final s = _sucursal;
    return l != null && s != null && s.stock >= _cantidad && _cantidad >= 1 && _cantidad <= l.disponibles;
  }

  double? get _diferencia {
    final l = _linea;
    final p = _prenda;
    if (l == null || p == null) return null;
    return (p.precio - l.precioPagado) * _cantidad;
  }

  Future<void> _enviar() async {
    final v = _variante;
    if (v == null || !_listo) return;
    setState(() {
      _enviando = true;
      _error = null;
    });
    try {
      final nuevo = await ref.read(cuentaRepositoryProvider).pedirCambio({
        'venta_id': o.ventaId,
        'item_linea_id': _lineaId,
        'cantidad': _cantidad,
        'producto_id': _prenda!.productoId,
        'talla_id': v.tallaId,
        'color_id': v.colorId,
        'sucursal_id': _sucursalId,
        'motivo': _motivo,
        'observaciones': _observaciones.text.trim().isEmpty ? null : _observaciones.text.trim(),
      });
      if (mounted) Navigator.of(context).pop(nuevo);
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  Widget _paso(String texto) => Padding(
        padding: const EdgeInsets.only(top: 18, bottom: 8),
        child: Text(texto, style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.3, color: tintaCuenta)),
      );

  Widget _opcion(String texto, String? detalle, bool activa, VoidCallback? onTap) {
    return InkWell(
      onTap: onTap,
      child: Opacity(
        opacity: onTap == null && !activa ? 0.45 : 1,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: activa ? _marca : Colors.white,
            border: Border.all(color: activa ? _marca : const Color(0xFFDDDDDD)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(texto, style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600, color: activa ? Colors.white : tintaCuenta)),
              if (detalle != null)
                Text(detalle, style: GoogleFonts.inter(fontSize: 10.5, color: activa ? Colors.white70 : grisCuenta)),
            ],
          ),
        ),
      ),
    );
  }

  /// Todas las prendas de la tienda con stock, en grilla (se ven todas).
  Widget _grillaPrendas(PrendaCambio? elegida) {
    return LayoutBuilder(
      builder: (context, c) {
        final columnas = c.maxWidth >= 520 ? 4 : 3;
        final ancho = (c.maxWidth - 10 * (columnas - 1)) / columnas;
        return Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final pr in o.prendas)
              SizedBox(
                width: ancho,
                child: InkWell(
                  onTap: () => _elegirPrenda(pr),
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      border: Border.all(color: elegida?.productoId == pr.productoId ? _marca : bordeCuenta, width: elegida?.productoId == pr.productoId ? 2 : 1),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        AspectRatio(
                          aspectRatio: 3 / 4,
                          child: pr.imagenUrl == null
                              ? Container(color: const Color(0xFFF3F3F3))
                              : CachedNetworkImage(imageUrl: resolveImageUrl(pr.imagenUrl!), fit: BoxFit.cover, width: double.infinity),
                        ),
                        Padding(
                          padding: const EdgeInsets.all(6),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(pr.nombre,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: GoogleFonts.inter(fontSize: 11, height: 1.25, fontWeight: FontWeight.w700, color: tintaCuenta)),
                              const SizedBox(height: 2),
                              Text('Bs ${bs(pr.precio)}', style: GoogleFonts.inter(fontSize: 11, color: grisOscuroCuenta)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  /// Lo que pasa con la plata: paga la diferencia, se le devuelve (y como) o nada.
  Widget _resumenDiferencia(double dif) {
    final String texto;
    if (dif > 0) {
      texto = 'La prenda nueva cuesta más: pagas la diferencia cuando la tienda apruebe el cambio.';
    } else if (dif < 0) {
      texto = o.reembolso == 'paypal'
          ? 'La prenda nueva cuesta menos: te devolvemos la diferencia a tu PayPal cuando la tienda apruebe el cambio.'
          : 'La prenda nueva cuesta menos: te devolvemos la diferencia en efectivo cuando recojas tu prenda en la sucursal.';
    } else {
      texto = 'Mismo precio: no pagas ni te devolvemos nada.';
    }
    return Container(
      margin: const EdgeInsets.only(top: 6),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: _marca.withValues(alpha: 0.07), border: Border(left: BorderSide(color: _marca, width: 3))),
      child: Row(
        children: [
          Expanded(child: Text(texto, style: GoogleFonts.inter(fontSize: 12.5, height: 1.45, color: tintaCuenta))),
          const SizedBox(width: 12),
          Text(dif == 0 ? 'Sin diferencia' : '${dif > 0 ? '' : '+ '}Bs ${bs(dif.abs())}',
              style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w800, color: dif < 0 ? verdeCuenta : _marca)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = _linea;
    final p = _prenda;
    final v = _variante;
    final s = _sucursal;
    final dif = _diferencia;
    final tallas = <int, String>{for (final x in p?.variantes ?? <VarianteCambio>[]) x.tallaId: x.tallaCodigo};

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Flexible(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (!o.puedeCambiar) ...[
                  const SizedBox(height: 16),
                  AvisoCuenta(o.motivoNo ?? 'Ya cambiaste todas las prendas de esta compra.', error: true),
                ] else ...[
                  _paso('1. ¿Qué prenda quieres cambiar?'),
                  for (final linea in o.lineas)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: InkWell(
                        onTap: linea.disponibles < 1
                            ? null
                            : () => setState(() {
                                  _lineaId = linea.itemLineaId;
                                  _cantidad = 1;
                                }),
                        child: Opacity(
                          opacity: linea.disponibles < 1 ? 0.5 : 1,
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: _lineaId == linea.itemLineaId ? _marca.withValues(alpha: 0.06) : Colors.white,
                              border: Border.all(color: _lineaId == linea.itemLineaId ? _marca : bordeCuenta),
                            ),
                            child: Row(
                              children: [
                                Icon(
                                  _lineaId == linea.itemLineaId ? Icons.radio_button_checked : Icons.radio_button_unchecked,
                                  size: 20,
                                  color: _marca,
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(linea.productoNombre,
                                          style: GoogleFonts.inter(fontSize: 13.5, fontWeight: FontWeight.w700, color: tintaCuenta)),
                                      Text(
                                        '${linea.tallaCodigo} · ${linea.colorNombre} · pagaste Bs ${bs(linea.precioPagado)}${linea.disponibles < 1 ? ' · ya la cambiaste' : ''}',
                                        style: GoogleFonts.inter(fontSize: 11.5, color: grisCuenta),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  if (l != null) ...[
                    if (l.disponibles > 1) ...[
                      _paso('Cuántas'),
                      Row(
                        children: [
                          IconButton(onPressed: _cantidad > 1 ? () => setState(() => _cantidad--) : null, icon: const Icon(Icons.remove)),
                          Text('$_cantidad', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700)),
                          IconButton(
                            onPressed: _cantidad < l.disponibles ? () => setState(() => _cantidad++) : null,
                            icon: const Icon(Icons.add),
                          ),
                        ],
                      ),
                    ],
                    _paso('2. ¿Por cuál? (${o.prendas.length} ${o.prendas.length == 1 ? 'prenda' : 'prendas'} con stock en ${o.tiendaNombre})'),
                    if (o.prendas.isEmpty)
                      vacioCuenta('No hay otras prendas con stock en esta tienda por ahora.')
                    else
                      _grillaPrendas(p),
                    if (p != null) ...[
                      _paso('3. Talla'),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final t in tallas.entries)
                            _opcion(t.value, null, _tallaId == t.key, _tallaDisponible(p, t.key) ? () => _elegirTalla(t.key) : null),
                        ],
                      ),
                      if (_tallaId != null) ...[
                        _paso('4. Color'),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final c in p.variantes.where((x) => x.tallaId == _tallaId))
                              _opcion(
                                c.colorNombre,
                                _esLaMisma(p, c) ? 'la que tienes' : !_colorDisponible(p, c) ? 'sin stock' : 'quedan ${c.stock}',
                                _colorId == c.colorId,
                                _colorDisponible(p, c) ? () => _elegirColor(c) : null,
                              ),
                          ],
                        ),
                      ],
                      if (v != null) ...[
                        _paso('5. ¿Dónde la recoges?'),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final su in v.sucursales)
                              _opcion(
                                su.sucursalNombre,
                                '${su.stock < _cantidad ? 'sin stock' : 'quedan ${su.stock}'}${su.sucursalId == o.sucursalId ? ' · donde compraste' : ''}',
                                _sucursalId == su.sucursalId,
                                su.stock >= _cantidad ? () => setState(() => _sucursalId = su.sucursalId) : null,
                              ),
                          ],
                        ),
                      ],
                      if (s != null && v != null) ...[
                        const SizedBox(height: 14),
                        Text.rich(
                          TextSpan(
                            text: 'Te llevas: ',
                            children: [
                              TextSpan(text: p.nombre, style: const TextStyle(fontWeight: FontWeight.w700)),
                              const TextSpan(text: ', talla '),
                              TextSpan(text: v.tallaCodigo, style: const TextStyle(fontWeight: FontWeight.w700)),
                              const TextSpan(text: ', color '),
                              TextSpan(text: v.colorNombre, style: const TextStyle(fontWeight: FontWeight.w700)),
                              const TextSpan(text: '. La recoges en '),
                              TextSpan(text: s.sucursalNombre, style: const TextStyle(fontWeight: FontWeight.w700)),
                              const TextSpan(text: ' y ahí entregas la prenda que devuelves.'),
                            ],
                          ),
                          style: GoogleFonts.inter(fontSize: 12.5, height: 1.45, color: tintaCuenta),
                        ),
                      ],
                    ],
                    _paso('6. Motivo'),
                    DropdownButtonFormField<String>(
                      initialValue: _motivo,
                      decoration: decoracionCampo(),
                      style: GoogleFonts.inter(fontSize: 14, color: tintaCuenta),
                      items: const [
                        DropdownMenuItem(value: 'talla', child: Text('No me quedó la talla')),
                        DropdownMenuItem(value: 'color', child: Text('Prefiero otro color')),
                        DropdownMenuItem(value: 'modelo', child: Text('Prefiero otro modelo')),
                        DropdownMenuItem(value: 'defecto', child: Text('Tiene un defecto')),
                        DropdownMenuItem(value: 'otro', child: Text('Otro motivo')),
                      ],
                      onChanged: (m) => setState(() => _motivo = m ?? _motivo),
                    ),
                    const SizedBox(height: 12),
                    etiquetaCampo('Detalles (opcional)'),
                    TextField(
                      controller: _observaciones,
                      maxLines: 2,
                      maxLength: 500,
                      style: GoogleFonts.inter(fontSize: 14, color: tintaCuenta),
                      decoration: decoracionCampo(),
                    ),
                    if (dif != null) _resumenDiferencia(dif),
                  ],
                  if (_error != null) ...[const SizedBox(height: 12), AvisoCuenta(_error!, error: true)],
                ],
              ],
            ),
          ),
        ),
        // Botones fijos abajo, por encima de los botones del celular.
        Container(
          padding: EdgeInsets.fromLTRB(20, 12, 20, 12 + MediaQuery.viewPaddingOf(context).bottom),
          decoration: const BoxDecoration(
            color: Colors.white,
            border: Border(top: BorderSide(color: bordeCuenta)),
          ),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: _marca,
                    side: BorderSide(color: _marca),
                    shape: const RoundedRectangleBorder(),
                    minimumSize: const Size.fromHeight(48),
                    textStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5),
                  ),
                  child: const Text('CERRAR'),
                ),
              ),
              if (o.puedeCambiar) ...[
                const SizedBox(width: 10),
                Expanded(
                  flex: 2,
                  child: FilledButton(
                    onPressed: !_listo || _enviando ? null : _enviar,
                    style: FilledButton.styleFrom(
                      backgroundColor: _marca,
                      foregroundColor: Colors.white,
                      disabledBackgroundColor: _marca.withValues(alpha: 0.4),
                      disabledForegroundColor: Colors.white,
                      shape: const RoundedRectangleBorder(),
                      minimumSize: const Size.fromHeight(48),
                      textStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5),
                    ),
                    child: Text(_enviando ? 'ENVIANDO…' : 'PEDIR EL CAMBIO'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
