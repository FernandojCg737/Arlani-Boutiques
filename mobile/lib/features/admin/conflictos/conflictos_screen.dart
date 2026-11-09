import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';
import '../../auth/auth_provider.dart';
import '../../offline/offline_modelos.dart' show estadoOperacion;
import '../widgets/admin_widgets.dart';
import '../widgets/dialogos.dart';

const _filtros = {
  'conflicto': 'En conflicto',
  '': 'Todas',
  'confirmada': 'Confirmadas',
  'resuelta': 'Resueltas',
  'anulada': 'Anuladas',
  'rechazada': 'Rechazadas',
  'pagada': 'Compras pagadas',
  'por_pagar': 'Compras por pagar',
  'en_espera': 'En espera de stock',
};

/// CU24 Operaciones offline y conflictos (`/admin/conflictos` de la web): lo
/// que llego de los dispositivos sin conexion; si no habia stock, una venta o
/// reserva queda en conflicto (se ajusta o se anula) y una compra de cliente
/// espera en la cola de stock.
class ConflictosScreen extends ConsumerStatefulWidget {
  const ConflictosScreen({super.key});

  @override
  ConsumerState<ConflictosScreen> createState() => _ConflictosScreenState();
}

class _ConflictosScreenState extends ConsumerState<ConflictosScreen> {
  String _filtro = 'conflicto';
  List<Map<String, dynamic>> _ops = [];
  List<Map<String, dynamic>> _cola = [];
  bool _cargando = true;
  String? _error;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final ops = await _dio.get('/offline/operaciones', queryParameters: {if (_filtro.isNotEmpty) 'estado': _filtro});
      final cola = _filtro == 'conflicto'
          ? (await _dio.get('/offline/operaciones', queryParameters: {'estado': 'en_espera'})).data as List
          : const [];
      setState(() {
        _ops = (ops.data as List).cast<Map<String, dynamic>>();
        _cola = cola.cast<Map<String, dynamic>>()..sort((a, b) => '${a['registrada_en']}'.compareTo('${b['registrada_en']}'));
      });
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  String _tipo(Map<String, dynamic> o) =>
      o['tipo'] == 'venta' ? 'Venta de contado' : o['tipo'] == 'pedido' ? 'Compra del cliente' : 'Reserva';

  Future<void> _resolver(Map<String, dynamic> o) async {
    final ok = await Navigator.of(context).push<bool>(MaterialPageRoute(builder: (_) => _Resolver(op: o, dio: _dio)));
    if (ok == true) _cargar();
  }

  Widget _faltas(Map<String, dynamic> o) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final c in (o['conflicto'] as List? ?? []))
          Text('${c['producto']} (${c['talla']}, ${c['color']}): pidió ${c['pedido']}, hay ${c['disponible']}',
              style: const TextStyle(color: Color(0xFFB3261E), fontSize: 12.5)),
      ]);

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final puedeResolver = auth.isAdministrador || auth.hasPermiso('2P-CU14');
    return AdminScaffold(
      title: 'OPERACIONES OFFLINE',
      body: RefreshIndicator(
        onRefresh: _cargar,
        child: ListView(padding: const EdgeInsets.only(bottom: 24), children: [
          SizedBox(
            height: 52,
            child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8), children: [
              for (final f in _filtros.entries)
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ChoiceChip(
                    label: Text(f.value),
                    selected: _filtro == f.key,
                    onSelected: (_) {
                      _filtro = f.key;
                      _cargar();
                    },
                  ),
                ),
            ]),
          ),
          if (_error != null) AdminErrorBanner(message: _error!),
          if (_cargando)
            const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator()))
          else ...[
            if (_ops.isEmpty)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(_filtro == 'conflicto' ? 'No hay conflictos de sincronización.' : 'No hay operaciones con este estado.'),
              ),
            for (final o in _ops)
              AdminCard(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(child: Text('${_tipo(o)} #${o['numero'] ?? o['id']}', style: const TextStyle(fontWeight: FontWeight.w800))),
                    NeutralBadge(estadoOperacion[o['estado']] ?? o['estado'].toString()),
                  ]),
                  Text('${o['sucursal_nombre'] ?? ''} · ${o['usuario_nombre'] ?? ''} · ${fechaTexto(o['registrada_en'])}',
                      style: const TextStyle(fontSize: 12)),
                  const SizedBox(height: 6),
                  for (final i in (o['items'] as List))
                    Text('${i['cantidad']}× ${i['producto']} (${i['talla']}, ${i['color']})', style: const TextStyle(fontSize: 13)),
                  if (o['cliente_nombre'] != null) Text('Cliente: ${o['cliente_nombre']}', style: const TextStyle(fontSize: 12)),
                  Text('Total ${bsTexto(o['total'])}', style: const TextStyle(fontWeight: FontWeight.w700)),
                  if (o['estado'] == 'conflicto' || o['estado'] == 'en_espera') _faltas(o),
                  if (o['resolucion'] != null) Text('${o['resolucion']} — ${o['resuelta_por_nombre'] ?? ''}', style: const TextStyle(fontSize: 12)),
                  if (o['resolucion'] == null && o['mensaje'] != null && o['estado'] != 'conflicto')
                    Text(o['mensaje'].toString(), style: const TextStyle(fontSize: 12)),
                  if (o['estado'] == 'conflicto' && puedeResolver)
                    Align(alignment: Alignment.centerRight, child: FilledButton(onPressed: () => _resolver(o), child: const Text('RESOLVER'))),
                ]),
              ),
            if (_filtro == 'conflicto') ...[
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 18, 16, 4),
                child: Text('COLA DE ESPERA DE STOCK', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 0.5)),
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 16),
                child: Text('Compras de clientes sin stock al sincronizar: esperan su turno y se completan solas cuando vuelve el '
                    'stock; a los 7 días se cancelan sin cobrar nada.', style: TextStyle(fontSize: 12.5)),
              ),
              if (_cola.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('No hay compras esperando stock.')),
              for (var n = 0; n < _cola.length; n++)
                AdminCard(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('Turno ${n + 1} · Compra del cliente #${_cola[n]['numero'] ?? _cola[n]['id']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                    Text('${_cola[n]['usuario_nombre'] ?? ''} · ${_cola[n]['sucursal_nombre'] ?? ''} · ${fechaTexto(_cola[n]['registrada_en'])}',
                        style: const TextStyle(fontSize: 12)),
                    _faltas(_cola[n]),
                  ]),
                ),
            ],
          ],
        ]),
      ),
    );
  }
}

/// Resolver un conflicto: ajustar con lo que hay (otra talla, color o
/// cantidad) o anular con motivo.
class _Resolver extends StatefulWidget {
  const _Resolver({required this.op, required this.dio});
  final Map<String, dynamic> op;
  final Dio dio;

  @override
  State<_Resolver> createState() => _ResolverState();
}

class _ResolverState extends State<_Resolver> {
  List<Map<String, dynamic>> _disponibles = [];
  // Por linea: variante elegida ("talla-color" o "" = quitar) y cantidad.
  final List<String> _variante = [];
  final List<int> _cantidad = [];
  String _accion = 'ajustar';
  final _motivo = TextEditingController();
  bool _cargando = true;
  bool _guardando = false;
  String? _error;

  List get _items => widget.op['items'] as List;

  @override
  void initState() {
    super.initState();
    widget.dio.get('/offline/operaciones/${widget.op['id']}/opciones').then((r) {
      final d = (r.data['disponibles'] as List).cast<Map<String, dynamic>>();
      for (final i in _items) {
        final misma = d.where((x) => x['producto_id'] == i['producto_id'] && x['talla_id'] == i['talla_id'] && x['color_id'] == i['color_id']).firstOrNull;
        _variante.add(misma == null ? '' : '${misma['talla_id']}-${misma['color_id']}');
        _cantidad.add(misma == null ? i['cantidad'] as int : (i['cantidad'] as int).clamp(1, misma['stock'] as int));
      }
      setState(() {
        _disponibles = d;
        _cargando = false;
      });
    }, onError: (e) => setState(() {
          _error = extractErrorMessage(e);
          _cargando = false;
        }));
  }

  @override
  void dispose() {
    _motivo.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    Map<String, dynamic> cuerpo;
    if (_accion == 'anular') {
      if (_motivo.text.trim().length < 3) return setState(() => _error = 'Escribe el motivo de la anulación.');
      cuerpo = {'accion': 'anular', 'motivo': _motivo.text.trim()};
    } else {
      final items = <Map<String, dynamic>>[];
      for (var n = 0; n < _items.length; n++) {
        if (_variante[n].isEmpty) continue;
        final p = _variante[n].split('-').map(int.parse).toList();
        items.add({'producto_id': _items[n]['producto_id'], 'talla_id': p[0], 'color_id': p[1], 'cantidad': _cantidad[n], 'precio': _items[n]['precio']});
      }
      if (items.isEmpty) return setState(() => _error = 'Deja al menos una prenda, o anula la operación.');
      cuerpo = {'accion': 'ajustar', 'motivo': _motivo.text.trim().isEmpty ? null : _motivo.text.trim(), 'items': items};
    }
    setState(() {
      _guardando = true;
      _error = null;
    });
    try {
      await widget.dio.post('/offline/operaciones/${widget.op['id']}/resolver', data: cuerpo);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: 'RESOLVER #${widget.op['numero'] ?? widget.op['id']}',
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : ListView(padding: const EdgeInsets.all(16), children: [
              if (_error != null) AdminErrorBanner(message: _error!),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'ajustar', label: Text('Ajustar con lo que hay')),
                  ButtonSegment(value: 'anular', label: Text('Anular')),
                ],
                selected: {_accion},
                onSelectionChanged: (s) => setState(() => _accion = s.first),
              ),
              const SizedBox(height: 16),
              if (_accion == 'ajustar')
                for (var n = 0; n < _items.length; n++)
                  AdminCard(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('Pidió ${_items[n]['cantidad']}× ${_items[n]['producto']} (${_items[n]['talla']}, ${_items[n]['color']})'),
                      DropdownButton<String>(
                        isExpanded: true,
                        value: _variante[n],
                        items: [
                          const DropdownMenuItem(value: '', child: Text('Quitar esta prenda')),
                          for (final d in _disponibles.where((d) => d['producto_id'] == _items[n]['producto_id']))
                            DropdownMenuItem(
                              value: '${d['talla_id']}-${d['color_id']}',
                              child: Text('${d['talla']} · ${d['color']} (hay ${d['stock']})'),
                            ),
                        ],
                        onChanged: (v) => setState(() {
                          _variante[n] = v ?? '';
                          _cantidad[n] = 1;
                        }),
                      ),
                      if (_variante[n].isNotEmpty)
                        Row(children: [
                          IconButton(onPressed: _cantidad[n] > 1 ? () => setState(() => _cantidad[n]--) : null, icon: const Icon(Icons.remove)),
                          Text('${_cantidad[n]}'),
                          IconButton(onPressed: () => setState(() => _cantidad[n]++), icon: const Icon(Icons.add)),
                        ]),
                    ]),
                  )
              else
                Text(widget.op['tipo'] == 'venta'
                    ? 'La operación no se registra. Hay que devolverle al cliente los ${bsTexto(widget.op['total'])} que pagó.'
                    : 'La operación no se registra.'),
              const SizedBox(height: 12),
              TextField(controller: _motivo, maxLines: 2, decoration: InputDecoration(labelText: _accion == 'anular' ? 'Motivo' : 'Nota (opcional)')),
              const SizedBox(height: 16),
              FilledButton(
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
                onPressed: _guardando ? null : _guardar,
                child: Text(_guardando ? 'GUARDANDO...' : (_accion == 'ajustar' ? 'REGISTRAR AJUSTE' : 'ANULAR OPERACION')),
              ),
            ]),
    );
  }
}
