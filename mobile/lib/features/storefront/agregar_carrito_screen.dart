import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_client.dart';
import 'cart_provider.dart';
import 'reservas_repository.dart';

enum _Estado { cargando, formulario, enviando, listo, error, sinStock }

class _TallaSucursal {
  const _TallaSucursal({
    required this.tallaId,
    required this.tallaCodigo,
    required this.sucursalId,
    required this.sucursalNombre,
    required this.total,
  });

  final int tallaId;
  final String tallaCodigo;
  final int sucursalId;
  final String sucursalNombre;
  final int total;

  String get key => '$tallaId:$sucursalId';
}

/// Abre la ventanita de "Agregar al carrito" (el modal `agregar-carrito` de
/// la web) sobre la pagina del producto. [envolver] le pone el tema con el
/// color de la tienda dueña del producto.
Future<void> mostrarAgregarCarrito(
  BuildContext context, {
  required int productoId,
  required String productoNombre,
  Widget Function(Widget)? envolver,
}) {
  return showDialog<void>(
    context: context,
    barrierColor: Colors.black54,
    builder: (_) {
      final dialogo = AgregarCarritoScreen(productoId: productoId, productoNombre: productoNombre);
      return envolver == null ? dialogo : envolver(dialogo);
    },
  );
}

/// CU11, lado cliente: elegir talla/color/cantidad antes de agregar al
/// carrito -- el backend lo exige (no se puede agregar un producto "en
/// general", tiene que ser una combinacion con stock real). Reusa el mismo
/// endpoint de disponibilidad que ya usa Reservar (CU10).
///
/// La sucursal de retiro se elige ACA, por producto: la talla viene "atada"
/// a una sucursal (ej. "XL -- Sucursal Norte (Stock 10)"), y el color se
/// filtra a los que esa sucursal tiene en esa talla.
class AgregarCarritoScreen extends ConsumerStatefulWidget {
  const AgregarCarritoScreen({super.key, required this.productoId, required this.productoNombre});

  final int productoId;
  final String productoNombre;

  @override
  ConsumerState<AgregarCarritoScreen> createState() => _AgregarCarritoScreenState();
}

class _AgregarCarritoScreenState extends ConsumerState<AgregarCarritoScreen> {
  _Estado _estado = _Estado.cargando;
  List<DisponibilidadItem> _variantes = [];
  String? _tallaSucursalKey;
  int? _colorId;
  final _cantidadCtrl = TextEditingController(text: '1');
  String _error = '';

  int get _cantidad => int.tryParse(_cantidadCtrl.text.trim()) ?? 0;

  List<_TallaSucursal> get _tallasSucursal {
    final vistos = <String>{};
    final lista = <_TallaSucursal>[];
    for (final v in _variantes) {
      final key = '${v.tallaId}:${v.sucursalId}';
      if (!vistos.add(key)) continue;
      final total = _variantes
          .where((x) => x.tallaId == v.tallaId && x.sucursalId == v.sucursalId)
          .fold(0, (sum, x) => sum + x.cantidad);
      lista.add(_TallaSucursal(
        tallaId: v.tallaId,
        tallaCodigo: v.tallaCodigo,
        sucursalId: v.sucursalId,
        sucursalNombre: v.sucursalNombre,
        total: total,
      ));
    }
    return lista;
  }

  List<DisponibilidadItem> get _coloresParaTallaActual {
    final key = _tallaSucursalKey;
    if (key == null) return [];
    final partes = key.split(':');
    final tallaId = int.parse(partes[0]);
    final sucursalId = int.parse(partes[1]);
    return _variantes.where((v) => v.tallaId == tallaId && v.sucursalId == sucursalId).toList();
  }

  DisponibilidadItem? get _varianteActual {
    for (final v in _coloresParaTallaActual) {
      if (v.colorId == _colorId) return v;
    }
    return null;
  }

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  @override
  void dispose() {
    _cantidadCtrl.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    try {
      final opciones = await ref.read(reservasRepositoryProvider).disponibilidad(widget.productoId);
      if (!mounted) return;
      if (opciones.isEmpty) {
        setState(() => _estado = _Estado.sinStock);
        return;
      }
      final primero = opciones.first;
      setState(() {
        _variantes = opciones;
        _tallaSucursalKey = '${primero.tallaId}:${primero.sucursalId}';
        _colorId = primero.colorId;
        _estado = _Estado.formulario;
      });
    } catch (_) {
      if (mounted) setState(() => _estado = _Estado.error);
    }
  }

  Future<void> _enviar() async {
    final variante = _varianteActual;
    if (variante == null) return;
    if (_cantidad < 1 || _cantidad > variante.cantidad) {
      setState(() => _error = 'Elige una cantidad entre 1 y ${variante.cantidad}.');
      return;
    }
    setState(() {
      _estado = _Estado.enviando;
      _error = '';
    });
    try {
      await ref.read(cartProvider.notifier).agregar(
            productoId: widget.productoId,
            tallaId: variante.tallaId,
            colorId: variante.colorId,
            sucursalId: variante.sucursalId,
            cantidad: _cantidad,
          );
      if (mounted) setState(() => _estado = _Estado.listo);
    } catch (err) {
      if (mounted) {
        setState(() {
          _error = extractErrorMessage(err);
          _estado = _Estado.formulario;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // El color de la tienda dueña del producto (tema de la pagina del producto).
    final marca = Theme.of(context).colorScheme.primary;
    return Dialog(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.white,
      insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
      shape: const RoundedRectangleBorder(),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Stack(
          children: [
            SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(28, 30, 28, 28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(right: 28),
                    child: Text('AGREGAR AL CARRITO',
                        style: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.w800, letterSpacing: 0.4, color: marca)),
                  ),
                  const SizedBox(height: 4),
                  Text(widget.productoNombre, style: GoogleFonts.inter(fontSize: 13, color: const Color(0xFF777777))),
                  const SizedBox(height: 22),
                  _contenido(marca),
                ],
              ),
            ),
            Positioned(
              top: 8,
              right: 8,
              child: IconButton(
                tooltip: 'Cerrar',
                icon: Icon(Icons.close, color: marca),
                onPressed: () => Navigator.of(context).pop(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _mensaje(String texto) =>
      Text(texto, style: GoogleFonts.inter(fontSize: 14, height: 1.5, color: const Color(0xFF555555)));

  Widget _contenido(Color marca) {
    switch (_estado) {
      case _Estado.cargando:
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Row(
            children: [
              SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: marca)),
              const SizedBox(width: 12),
              _mensaje('Cargando disponibilidad...'),
            ],
          ),
        );
      case _Estado.sinStock:
        return _mensaje('Este producto no tiene stock disponible en ninguna sucursal por ahora.');
      case _Estado.error:
        return _mensaje('No pudimos cargar la disponibilidad. Intenta de nuevo en unos segundos.');
      case _Estado.formulario:
      case _Estado.enviando:
        return _formulario(marca);
      case _Estado.listo:
        return _exito(marca);
    }
  }

  Widget _etiqueta(String texto) => Padding(
        padding: const EdgeInsets.only(bottom: 2),
        child: Text(texto,
            style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: const Color(0xFF999999))),
      );

  InputDecoration _subrayado(Color marca) => InputDecoration(
        isDense: true,
        filled: false,
        contentPadding: const EdgeInsets.symmetric(vertical: 10),
        border: const UnderlineInputBorder(borderSide: BorderSide(color: Color(0xFFDDDDDD))),
        enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Color(0xFFDDDDDD))),
        focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: marca)),
      );

  Widget _formulario(Color marca) {
    final estilo = GoogleFonts.inter(fontSize: 15, color: const Color(0xFF333333));
    final variante = _varianteActual;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_error.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(12),
            color: const Color(0xFFFDECEA),
            child: Text(_error, style: GoogleFonts.inter(color: const Color(0xFFB3261E), fontSize: 13)),
          ),
          const SizedBox(height: 16),
        ],
        _etiqueta('TALLA'),
        DropdownButtonFormField<String>(
          initialValue: _tallaSucursalKey,
          isExpanded: true,
          style: estilo,
          decoration: _subrayado(marca),
          items: [
            for (final t in _tallasSucursal)
              DropdownMenuItem(
                value: t.key,
                child: Text('${t.tallaCodigo} -- ${t.sucursalNombre} (Stock ${t.total})', overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: (key) {
            if (key == null) return;
            setState(() {
              _tallaSucursalKey = key;
              // La talla/sucursal nueva puede no tener el mismo color: se
              // pasa al primero que si tenga stock ahi.
              final partes = key.split(':');
              final tallaId = int.parse(partes[0]);
              final sucursalId = int.parse(partes[1]);
              _colorId = _variantes.firstWhere((v) => v.tallaId == tallaId && v.sucursalId == sucursalId).colorId;
              _cantidadCtrl.text = '1';
            });
          },
        ),
        const SizedBox(height: 22),
        _etiqueta('COLOR'),
        DropdownButtonFormField<int>(
          key: ValueKey(_tallaSucursalKey),
          initialValue: _colorId,
          isExpanded: true,
          style: estilo,
          decoration: _subrayado(marca),
          items: [
            for (final v in _coloresParaTallaActual)
              DropdownMenuItem(
                value: v.colorId,
                child: Text('${v.colorNombre} (${v.cantidad} disponibles)', overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: (colorId) {
            if (colorId == null) return;
            setState(() {
              _colorId = colorId;
              _cantidadCtrl.text = '1';
            });
          },
        ),
        const SizedBox(height: 22),
        _etiqueta('CANTIDAD'),
        TextField(
          controller: _cantidadCtrl,
          keyboardType: TextInputType.number,
          style: estilo,
          decoration: _subrayado(marca).copyWith(
            helperText: variante == null ? null : 'Hasta ${variante.cantidad}',
            helperStyle: GoogleFonts.inter(fontSize: 11, color: const Color(0xFF999999)),
          ),
        ),
        const SizedBox(height: 24),
        SizedBox(
          height: 48,
          child: FilledButton(
            onPressed: _estado == _Estado.enviando ? null : _enviar,
            style: FilledButton.styleFrom(
              backgroundColor: marca,
              foregroundColor: Colors.white,
              disabledBackgroundColor: marca.withValues(alpha: 0.6),
              disabledForegroundColor: Colors.white,
              shape: const RoundedRectangleBorder(),
              textStyle: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 0.6),
            ),
            child: Text(_estado == _Estado.enviando ? 'AGREGANDO...' : 'AGREGAR AL CARRITO'),
          ),
        ),
      ],
    );
  }

  Widget _exito(Color marca) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Icon(Icons.check_circle_outline, size: 44, color: marca),
        const SizedBox(height: 12),
        Text('Se agregó a tu carrito.',
            textAlign: TextAlign.center, style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700, color: const Color(0xFF333333))),
        const SizedBox(height: 20),
        SizedBox(
          height: 48,
          child: FilledButton(
            onPressed: () {
              final router = GoRouter.of(context);
              Navigator.of(context).pop();
              router.push('/carrito');
            },
            style: FilledButton.styleFrom(
              backgroundColor: marca,
              foregroundColor: Colors.white,
              shape: const RoundedRectangleBorder(),
              textStyle: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 0.6),
            ),
            child: const Text('IR AL CARRITO'),
          ),
        ),
        const SizedBox(height: 10),
        SizedBox(
          height: 48,
          child: OutlinedButton(
            onPressed: () => Navigator.of(context).pop(),
            style: OutlinedButton.styleFrom(
              foregroundColor: marca,
              side: BorderSide(color: marca),
              shape: const RoundedRectangleBorder(),
              textStyle: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 0.6),
            ),
            child: const Text('SEGUIR COMPRANDO'),
          ),
        ),
      ],
    );
  }
}
