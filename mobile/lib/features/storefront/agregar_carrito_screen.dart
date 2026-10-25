import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme.dart';
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

/// CU11, lado cliente: elegir talla/color/cantidad antes de agregar al
/// carrito -- el backend lo exige (no se puede agregar un producto "en
/// general", tiene que ser una combinacion con stock real). Reusa el mismo
/// endpoint de disponibilidad que ya usa Reservar (CU10).
///
/// Pedido explicito del usuario: la sucursal de retiro se elige ACA, por
/// producto -- ya no en el checkout. La talla viene "atada" a una sucursal
/// (ej. "XL -- Sucursal Norte, Stock 10"): elegirla fija ambas cosas de una,
/// y el color se filtra a los que esa sucursal tiene en esa talla.
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
  int _cantidad = 1;
  String _error = '';

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

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _enviar() async {
    final variante = _varianteActual;
    if (variante == null) return;

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
    return Scaffold(
      appBar: AppBar(title: const Text('AGREGAR AL CARRITO')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: _contenido(),
        ),
      ),
    );
  }

  Widget _contenido() {
    switch (_estado) {
      case _Estado.cargando:
        return const Center(child: CircularProgressIndicator());
      case _Estado.sinStock:
        return const Center(
          child: Text(
            'Este producto no tiene stock disponible en ninguna sucursal por ahora.',
            textAlign: TextAlign.center,
          ),
        );
      case _Estado.error:
        return const Center(
          child: Text('No pudimos cargar la disponibilidad. Intenta de nuevo en unos segundos.'),
        );
      case _Estado.formulario:
      case _Estado.enviando:
        return _formulario();
      case _Estado.listo:
        return _exito();
    }
  }

  Widget _formulario() {
    return ListView(
      children: [
        Text(widget.productoNombre, style: const TextStyle(color: Colors.grey, fontSize: 13)),
        const SizedBox(height: 20),

        if (_error.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(12),
            color: const Color(0xFFFDECEA),
            child: Text(_error, style: const TextStyle(color: Color(0xFFB3261E), fontSize: 13)),
          ),
          const SizedBox(height: 16),
        ],

        const Text('TALLA', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.grey)),
        const SizedBox(height: 6),
        DropdownButtonFormField<String>(
          initialValue: _tallaSucursalKey,
          isExpanded: true,
          items: _tallasSucursal
              .map((t) => DropdownMenuItem(
                    value: t.key,
                    child: Text(
                      '${t.tallaCodigo} -- ${t.sucursalNombre} (Stock ${t.total})',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ))
              .toList(),
          onChanged: (key) {
            if (key == null) return;
            setState(() {
              _tallaSucursalKey = key;
              // La talla/sucursal nueva puede no tener el mismo color que
              // estaba elegido -- se cae al primero que si tenga stock ahi.
              final partes = key.split(':');
              final tallaId = int.parse(partes[0]);
              final sucursalId = int.parse(partes[1]);
              _colorId = _variantes
                  .firstWhere((v) => v.tallaId == tallaId && v.sucursalId == sucursalId)
                  .colorId;
              _cantidad = 1;
            });
          },
        ),
        const SizedBox(height: 20),

        const Text('COLOR', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.grey)),
        const SizedBox(height: 6),
        DropdownButtonFormField<int>(
          initialValue: _colorId,
          isExpanded: true,
          items: _coloresParaTallaActual
              .map((v) => DropdownMenuItem(value: v.colorId, child: Text('${v.colorNombre} (${v.cantidad} disponibles)', overflow: TextOverflow.ellipsis)))
              .toList(),
          onChanged: (colorId) {
            if (colorId == null) return;
            setState(() {
              _colorId = colorId;
              _cantidad = 1;
            });
          },
        ),
        const SizedBox(height: 20),

        const Text('CANTIDAD', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.grey)),
        const SizedBox(height: 6),
        Row(
          children: [
            IconButton(
              onPressed: _cantidad > 1 ? () => setState(() => _cantidad--) : null,
              icon: const Icon(Icons.remove_circle_outline),
            ),
            Text('$_cantidad', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            IconButton(
              onPressed: (_varianteActual != null && _cantidad < _varianteActual!.cantidad)
                  ? () => setState(() => _cantidad++)
                  : null,
              icon: const Icon(Icons.add_circle_outline),
            ),
          ],
        ),
        const SizedBox(height: 28),

        ElevatedButton(
          onPressed: _estado == _Estado.enviando ? null : _enviar,
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.brandDark,
            minimumSize: const Size.fromHeight(48),
            shape: const RoundedRectangleBorder(),
          ),
          child: Text(_estado == _Estado.enviando ? 'AGREGANDO...' : 'AGREGAR AL CARRITO'),
        ),
      ],
    );
  }

  Widget _exito() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.check_circle_outline, size: 48, color: AppColors.brandDark),
          const SizedBox(height: 16),
          const Text('Se agrego a tu carrito.', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 20),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              OutlinedButton(
                onPressed: () => Navigator.of(context).pop(),
                style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder()),
                child: const Text('SEGUIR COMPRANDO'),
              ),
              const SizedBox(width: 12),
              ElevatedButton(
                onPressed: () => context.push('/carrito'),
                style: ElevatedButton.styleFrom(shape: const RoundedRectangleBorder()),
                child: const Text('IR AL CARRITO'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
