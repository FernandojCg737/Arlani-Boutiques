import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';
import '../../auth/auth_provider.dart';
import '../../empezar/panel_paypal.dart';
import '../widgets/admin_widgets.dart';
import '../widgets/dialogos.dart';

/// Mi suscripcion (`/admin/suscripcion` de la web, solo el Administrador): el
/// plan, cuanto le queda, sus limites, el historial y renovar o cambiar de
/// plan pagando con PayPal en el panel incrustado.
class SuscripcionScreen extends ConsumerStatefulWidget {
  const SuscripcionScreen({super.key});

  @override
  ConsumerState<SuscripcionScreen> createState() => _SuscripcionScreenState();
}

class _SuscripcionScreenState extends ConsumerState<SuscripcionScreen> {
  Map<String, dynamic>? _s;
  String? _plan;
  String _periodo = 'mensual';
  Map<String, dynamic>? _cotizacion;
  (String, String)? _panel; // (order_id, approve_url)
  bool _cargando = true;
  bool _procesando = false;
  String? _error;
  String? _aviso;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final r = await _dio.get('/mi-empresa/suscripcion');
      setState(() {
        _s = r.data as Map<String, dynamic>;
        _plan ??= _s?['plan_codigo']?.toString() ?? (_s?['planes'] as List).first['codigo'].toString();
      });
      _cotizar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _cotizar() async {
    if (_plan == null) return;
    try {
      final r = await _dio.post('/mi-empresa/suscripcion/cotizar', data: {'plan': _plan, 'periodo': _periodo});
      setState(() => _cotizacion = r.data as Map<String, dynamic>);
    } catch (e) {
      setState(() => _cotizacion = null);
    }
  }

  Future<void> _pagar() async {
    setState(() {
      _procesando = true;
      _error = null;
    });
    try {
      final r = await _dio.post('/mi-empresa/suscripcion/orden', data: {'plan': _plan, 'periodo': _periodo});
      final url = r.data['approve_url'] as String?;
      if (url == null) throw StateError('PayPal no devolvió el enlace de pago.');
      setState(() => _panel = (r.data['order_id'].toString(), url));
    } catch (e) {
      setState(() => _error = e is StateError ? e.message : extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _alTerminar(String? orderId) async {
    setState(() => _panel = null);
    if (orderId == null) return setState(() => _error = 'Cancelaste el pago. Puedes intentarlo de nuevo.');
    setState(() => _procesando = true);
    try {
      final r = await _dio.post('/mi-empresa/suscripcion/confirmar', data: {'plan': _plan, 'periodo': _periodo, 'order_id': orderId});
      setState(() {
        _s = r.data as Map<String, dynamic>;
        _aviso = '¡Listo! Tu suscripción quedó al día.';
      });
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _s;
    return AdminScaffold(
      title: 'MI SUSCRIPCION',
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : ListView(padding: const EdgeInsets.only(bottom: 32), children: [
              if (_error != null) AdminErrorBanner(message: _error!),
              if (_aviso != null)
                Container(margin: const EdgeInsets.all(16), padding: const EdgeInsets.all(12), color: const Color(0xFFEAF6EC), child: Text(_aviso!)),
              if (s != null) ...[
                AdminCard(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Expanded(
                        child: Text(s['plan_nombre']?.toString() ?? 'Sin plan vigente',
                            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                      ),
                      NeutralBadge(s['operativa'] == true ? 'ACTIVA' : 'VENCIDA'),
                    ]),
                    if (s['fecha_fin'] != null)
                      AdminInfoRow('Vence', '${fechaTexto(s['fecha_fin'], hora: false)} (${s['dias_restantes'] ?? 0} días)'),
                    if (s['periodo'] != null) AdminInfoRow('Periodo', '${s['periodo']} · ${bsTexto(s['monto'])}'),
                    AdminInfoRow('Sucursales', '${s['sucursales_usadas']} de ${s['max_sucursales'] ?? '—'}'),
                    AdminInfoRow('Personal / clientes', '${s['personal']} / ${s['clientes']}'),
                    if (s['comision_pct'] != null) AdminInfoRow('Comisión por venta', '${s['comision_pct']} %'),
                  ]),
                ),
                AdminCard(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Renovar o cambiar de plan', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                    const SizedBox(height: 8),
                    for (final p in (s['planes'] as List).cast<Map<String, dynamic>>())
                      RadioListTile<String>(
                        contentPadding: EdgeInsets.zero,
                        value: p['codigo'].toString(),
                        groupValue: _plan,
                        title: Text('${p['nombre']} · ${bsTexto(p['precio_mensual'])}/mes'),
                        subtitle: Text([
                          'hasta ${p['max_sucursales']} sucursales',
                          if (p['operacion_offline'] == true) 'offline',
                          if (p['backups'] == true) 'backups',
                          if (p['ia_generativa'] == true) 'IA',
                          if (p['live_commerce'] == true) 'live commerce',
                        ].join(' · ')),
                        onChanged: (v) {
                          setState(() => _plan = v);
                          _cotizar();
                        },
                      ),
                    SegmentedButton<String>(
                      segments: const [ButtonSegment(value: 'mensual', label: Text('Mensual')), ButtonSegment(value: 'anual', label: Text('Anual'))],
                      selected: {_periodo},
                      onSelectionChanged: (v) {
                        setState(() => _periodo = v.first);
                        _cotizar();
                      },
                    ),
                    if (_cotizacion != null) ...[
                      const SizedBox(height: 10),
                      Text('Total: ${bsTexto(_cotizacion!['monto_bob'])} (USD ${_cotizacion!['monto_usd']})',
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                      if (double.tryParse('${_cotizacion!['monto_bob']}') != double.tryParse('${_cotizacion!['plan_bob']}'))
                        const Text('Incluye las comisiones pendientes de tus ventas.', style: TextStyle(fontSize: 12)),
                    ],
                    const SizedBox(height: 12),
                    if (_panel != null)
                      PanelPaypal(
                        key: ValueKey(_panel!.$1),
                        url: _panel!.$2,
                        orderId: _panel!.$1,
                        alto: (MediaQuery.sizeOf(context).height * 0.75).clamp(460.0, 680.0),
                        alTerminar: _alTerminar,
                      )
                    else
                      FilledButton(
                        style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
                        onPressed: _procesando || _cotizacion == null ? null : _pagar,
                        child: Text(_procesando ? 'PROCESANDO...' : 'PAGAR CON PAYPAL'),
                      ),
                  ]),
                ),
                const Padding(padding: EdgeInsets.fromLTRB(16, 12, 16, 4), child: Text('HISTORIAL', style: TextStyle(fontWeight: FontWeight.w800))),
                for (final h in (s['historial'] as List).cast<Map<String, dynamic>>())
                  AdminCard(
                    child: Row(children: [
                      Expanded(
                        child: Text('${h['plan_nombre']} · ${h['periodo']} · ${bsTexto(h['monto'])}\n'
                            '${fechaTexto(h['fecha_inicio'], hora: false)} – ${fechaTexto(h['fecha_fin'], hora: false)}'),
                      ),
                      NeutralBadge(h['estado'].toString().toUpperCase()),
                    ]),
                  ),
              ],
            ]),
    );
  }
}
