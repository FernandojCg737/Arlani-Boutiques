import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';
import '../../auth/auth_provider.dart';
import '../widgets/admin_widgets.dart';
import '../widgets/dialogos.dart';

/// CU22 Arqueo y cierre de caja (`/admin/caja` de la web): la caja fisica de
/// cada sucursal (abrir con fondo inicial, ingresos y retiros, cerrar contando
/// el efectivo), la caja online del dia y el historial con sus ventas.
class CajaScreen extends ConsumerStatefulWidget {
  const CajaScreen({super.key});

  @override
  ConsumerState<CajaScreen> createState() => _CajaScreenState();
}

class _CajaScreenState extends ConsumerState<CajaScreen> {
  Map<String, dynamic>? _panel;
  List<Map<String, dynamic>> _historial = [];
  bool _cargando = true;
  String? _error;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _error = null);
    try {
      final panel = await _dio.get('/cajas/panel');
      final historial = await _dio.get('/cajas');
      setState(() {
        _panel = panel.data as Map<String, dynamic>;
        _historial = (historial.data as List).cast<Map<String, dynamic>>();
      });
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _accion(Future<void> Function() f) async {
    try {
      await f();
      await _cargar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  Future<void> _abrir(Map<String, dynamic> sucursal) async {
    final r = await formularioDialogo(context,
        titulo: 'Abrir caja · ${sucursal['nombre']}',
        texto: 'Con cuánto efectivo empieza la caja (fondo de cambio).',
        campos: const [CampoDialogo('monto', 'Monto inicial (Bs)', numero: true, inicial: '0')],
        aceptar: 'Abrir caja');
    if (r == null) return;
    await _accion(() => _dio.post('/cajas/abrir', data: {'sucursal_id': sucursal['id'], 'monto_inicial': r['monto']}));
  }

  Future<void> _movimiento(Map<String, dynamic> caja, String tipo) async {
    final r = await formularioDialogo(context,
        titulo: tipo == 'ingreso' ? 'Ingreso de efectivo' : 'Retiro de efectivo',
        campos: const [CampoDialogo('monto', 'Monto (Bs)', numero: true), CampoDialogo('motivo', 'Motivo')],
        aceptar: 'Registrar');
    if (r == null) return;
    await _accion(() => _dio.post('/cajas/${caja['id']}/movimientos', data: {'tipo': tipo, 'monto': r['monto'], 'motivo': r['motivo']}));
  }

  Future<void> _cerrar(Map<String, dynamic> caja) async {
    final esperado = caja['resumen']?['efectivo_esperado'];
    final r = await formularioDialogo(context,
        titulo: 'Cerrar caja',
        texto: 'Efectivo esperado: ${bsTexto(esperado)}. Cuenta el efectivo y escribe cuánto hay.',
        campos: const [
          CampoDialogo('contado', 'Efectivo contado (Bs)', numero: true),
          CampoDialogo('obs', 'Observación (opcional)', lineas: 2),
        ],
        aceptar: 'Cerrar caja');
    if (r == null) return;
    await _accion(() async {
      final res = await _dio.post('/cajas/${caja['id']}/cerrar',
          data: {'efectivo_contado': r['contado'], 'observacion': r['obs']!.isEmpty ? null : r['obs']});
      final dif = double.tryParse('${res.data['diferencia']}') ?? 0;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(dif == 0 ? 'Caja cerrada: cuadra exacto.' : 'Caja cerrada con diferencia de ${bsTexto(dif)}.'),
        ));
      }
    });
  }

  Future<void> _detalle(Map<String, dynamic> caja) async {
    final res = await _dio.get('/cajas/${caja['id']}');
    if (!mounted) return;
    final d = res.data as Map<String, dynamic>;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.8,
        child: ListView(padding: const EdgeInsets.all(16), children: [
          Text(_titulo(d), style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          ..._resumen(d),
          const Divider(height: 28),
          const Text('Movimientos', style: TextStyle(fontWeight: FontWeight.w800)),
          if ((d['movimientos'] as List).isEmpty) const Text('Sin movimientos.'),
          for (final m in d['movimientos'] as List)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text('${m['tipo'] == 'ingreso' ? '+' : '−'} ${bsTexto(m['monto'])} · ${m['motivo']}'),
              subtitle: Text('${m['usuario_nombre'] ?? ''} · ${fechaTexto(m['fecha'])}'),
            ),
          const Divider(height: 28),
          Text('Ventas (${(d['ventas_detalle'] as List).length})', style: const TextStyle(fontWeight: FontWeight.w800)),
          for (final v in d['ventas_detalle'] as List)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text('#${v['numero'] ?? v['id']} · ${v['cliente']} · ${bsTexto(v['total'])}'),
              subtitle: Text('${v['metodo_pago'] ?? '—'} · ${v['origen']} · ${fechaTexto(v['fecha'])}'
                  '${v['fuera_de_arqueo'] == true ? ' · fuera de arqueo' : ''}'),
            ),
        ]),
      ),
    );
  }

  String _titulo(Map<String, dynamic> c) =>
      c['tipo'] == 'online' ? 'Caja online · ${fechaTexto(c['fecha'], hora: false)}' : 'Caja ${c['sucursal_nombre'] ?? ''} · ${fechaTexto(c['abierta_en'])}';

  List<Widget> _resumen(Map<String, dynamic> c) {
    final r = c['resumen'] as Map<String, dynamic>? ?? {};
    return [
      if (c['tipo'] != 'online') AdminInfoRow('Abierta por', '${c['abierta_por_nombre'] ?? '—'} · ${fechaTexto(c['abierta_en'])}'),
      if (c['tipo'] != 'online') AdminInfoRow('Monto inicial', bsTexto(c['monto_inicial'])),
      AdminInfoRow('Ventas', '${r['ventas'] ?? 0} · ${bsTexto(r['total_ventas'])}'),
      AdminInfoRow('Efectivo', bsTexto(r['efectivo'])),
      AdminInfoRow('QR / PayPal / otros', '${bsTexto(r['qr'])} / ${bsTexto(r['paypal'])} / ${bsTexto(r['otros'])}'),
      if (c['tipo'] != 'online') AdminInfoRow('Ingresos / retiros', '${bsTexto(r['ingresos'])} / ${bsTexto(r['retiros'])}'),
      if (r['efectivo_esperado'] != null) AdminInfoRow('Efectivo esperado', bsTexto(r['efectivo_esperado'])),
      if (c['cerrada_en'] != null) ...[
        AdminInfoRow('Contado', bsTexto(c['efectivo_contado'])),
        AdminInfoRow('Diferencia', bsTexto(c['diferencia'])),
        AdminInfoRow('Cerrada por', '${c['cerrada_por_nombre'] ?? '—'} · ${fechaTexto(c['cerrada_en'])}'),
      ],
    ];
  }

  @override
  Widget build(BuildContext context) {
    final panel = _panel;
    final opera = panel?['puede_operar'] == true;
    return AdminScaffold(
      title: 'ARQUEO Y CIERRE DE CAJA',
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _cargar,
              child: ListView(padding: const EdgeInsets.only(bottom: 24), children: [
                if (_error != null) AdminErrorBanner(message: _error!),
                if (panel != null) ...[
                  for (final s in (panel['sucursales'] as List).cast<Map<String, dynamic>>())
                    AdminCard(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Expanded(child: Text(s['nombre'].toString(), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15))),
                          NeutralBadge(s['caja'] == null ? 'CERRADA' : 'ABIERTA'),
                        ]),
                        if (s['horario_atencion'] != null) Text(s['horario_atencion'].toString(), style: const TextStyle(fontSize: 12)),
                        const SizedBox(height: 8),
                        if (s['caja'] == null)
                          FilledButton(onPressed: opera ? () => _abrir(s) : null, child: const Text('ABRIR CAJA'))
                        else ...[
                          ..._resumen(s['caja'] as Map<String, dynamic>),
                          const SizedBox(height: 8),
                          Wrap(spacing: 8, runSpacing: 8, children: [
                            OutlinedButton(onPressed: opera ? () => _movimiento(s['caja'], 'ingreso') : null, child: const Text('INGRESO')),
                            OutlinedButton(onPressed: opera ? () => _movimiento(s['caja'], 'retiro') : null, child: const Text('RETIRO')),
                            FilledButton(onPressed: opera ? () => _cerrar(s['caja']) : null, child: const Text('CERRAR CAJA')),
                            TextButton(onPressed: () => _detalle(s['caja']), child: const Text('Ver detalle')),
                          ]),
                        ],
                      ]),
                    ),
                  if (panel['online'] != null)
                    AdminCard(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('Caja online de hoy', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                        const Text('Se abre y se cierra sola cada día con las ventas en línea.', style: TextStyle(fontSize: 12)),
                        const SizedBox(height: 8),
                        ..._resumen(panel['online'] as Map<String, dynamic>),
                        TextButton(onPressed: () => _detalle(panel['online']), child: const Text('Ver detalle')),
                      ]),
                    ),
                ],
                const Padding(
                  padding: EdgeInsets.fromLTRB(16, 16, 16, 4),
                  child: Text('HISTORIAL DE CAJAS', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 0.5)),
                ),
                for (final c in _historial)
                  AdminCard(
                    child: InkWell(
                      onTap: () => _detalle(c),
                      child: Row(children: [
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(_titulo(c), style: const TextStyle(fontWeight: FontWeight.w700)),
                            Text('${c['resumen']?['ventas'] ?? 0} ventas · ${bsTexto(c['resumen']?['total_ventas'])}'
                                '${c['diferencia'] != null ? ' · diferencia ${bsTexto(c['diferencia'])}' : ''}'),
                          ]),
                        ),
                        NeutralBadge(c['estado'].toString().toUpperCase()),
                      ]),
                    ),
                  ),
              ]),
            ),
    );
  }
}
