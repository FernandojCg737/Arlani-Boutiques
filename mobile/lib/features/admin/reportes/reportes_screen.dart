import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../../../core/api_client.dart';
import '../../auth/auth_provider.dart';
import '../widgets/admin_widgets.dart';
import '../widgets/dialogos.dart';
import 'reportes_comun.dart';

const _fijos = {
  'ventas': ('Reporte de ventas', 'Ventas del periodo por cliente, sucursal, tipo y método de pago.'),
  'asistencia': ('Reporte de asistencia', 'Marcados de asistencia del personal.'),
  'inventario': ('Reporte de inventario', 'Stock por sucursal, talla y color.'),
  'reservas': ('Reporte de reservas', 'Reservas del periodo y su estado.'),
  'productos': ('Reporte de productos', 'Productos más vendidos y su rendimiento.'),
};

/// CU16 Reportes y dashboards (`/admin/reportes` de la web): el dashboard, los
/// reportes fijos (se ven igual que en la web y se exportan en PDF, Excel, CSV
/// o HTML, o se envian por correo) y el reporte dinamico.
class ReportesScreen extends ConsumerStatefulWidget {
  const ReportesScreen({super.key});

  @override
  ConsumerState<ReportesScreen> createState() => _ReportesScreenState();
}

class _ReportesScreenState extends ConsumerState<ReportesScreen> {
  DateTime _hasta = DateTime.now();
  DateTime _desde = DateTime.now().subtract(const Duration(days: 30));
  Map<String, dynamic>? _dashboard;
  // CU18: pronostico de ventas de las proximas 4 semanas (modelo de ML).
  Map<String, dynamic>? _pronostico;
  String? _pronosticoError;
  List<Map<String, dynamic>> _fuentes = [];
  String? _fuente;
  final Set<String> _agrupar = {};
  final Set<String> _metricas = {};
  Map<String, dynamic>? _tabla;
  bool _generando = false;
  String? _error;

  Dio get _dio => ref.read(apiClientProvider).dio;
  String? get _correo => ref.read(authProvider).usuario?.email;

  String _iso(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  Map<String, dynamic> get _rango => {'fecha_desde': _iso(_desde), 'fecha_hasta': _iso(_hasta)};

  @override
  void initState() {
    super.initState();
    _dio.get('/reportes/dashboard').then((r) => mounted ? setState(() => _dashboard = r.data as Map<String, dynamic>) : null,
        onError: (e) => mounted ? setState(() => _error = extractErrorMessage(e)) : null);
    _dio.get('/reportes/pronostico').then((r) => mounted ? setState(() => _pronostico = r.data as Map<String, dynamic>) : null,
        onError: (e) => mounted ? setState(() => _pronosticoError = extractErrorMessage(e)) : null);
    _dio.get('/reportes/dinamico/fuentes').then((r) {
      if (!mounted) return;
      setState(() {
        _fuentes = (r.data as List).cast<Map<String, dynamic>>();
        if (_fuentes.isNotEmpty) _elegirFuente(_fuentes.first['clave'].toString());
      });
    }, onError: (_) {});
  }

  void _elegirFuente(String clave) {
    final f = _fuentes.firstWhere((x) => x['clave'] == clave);
    _fuente = clave;
    _agrupar
      ..clear()
      ..addAll((f['defecto']['agrupar'] as List).cast<String>());
    _metricas
      ..clear()
      ..addAll((f['defecto']['metricas'] as List).cast<String>());
    _tabla = null;
  }

  Future<void> _rangoFechas() async {
    final r = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2024),
      lastDate: DateTime.now(),
      initialDateRange: DateTimeRange(start: _desde, end: _hasta),
    );
    if (r != null) {
      setState(() {
        _desde = r.start;
        _hasta = r.end;
      });
    }
  }

  Future<void> _ver(String clave) async {
    try {
      final res = await _dio.get('/reportes/$clave/exportar',
          queryParameters: {..._rango, 'formato': 'html'}, options: Options(responseType: ResponseType.bytes));
      final html = utf8.decode(res.data as List<int>);
      if (!mounted) return;
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => AdminScaffold(
          title: _fijos[clave]!.$1.toUpperCase(),
          actions: [
            IconButton(
              icon: const Icon(Icons.ios_share),
              onPressed: () => exportarReporte(context, _dio, nombre: _fijos[clave]!.$1, ruta: '/reportes/$clave/exportar', params: _rango, correoInicial: _correo),
            ),
          ],
          body: WebViewWidget(controller: WebViewController()..loadHtmlString(html)),
        ),
      ));
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  Future<void> _generar() async {
    setState(() {
      _generando = true;
      _error = null;
    });
    try {
      final f = _fuentes.firstWhere((x) => x['clave'] == _fuente);
      final r = await _dio.post('/reportes/dinamico', data: {
        'fuente': _fuente,
        'agrupar': _agrupar.toList(),
        'metricas': _metricas.toList(),
        if (f['con_fechas'] == true) 'desde': _iso(_desde),
        if (f['con_fechas'] == true) 'hasta': _iso(_hasta),
      });
      setState(() => _tabla = r.data as Map<String, dynamic>);
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _generando = false);
    }
  }

  Widget _periodo() => ListTile(
        contentPadding: EdgeInsets.zero,
        leading: const Icon(Icons.date_range),
        title: Text('Del ${fechaTexto(_iso(_desde), hora: false)} al ${fechaTexto(_iso(_hasta), hora: false)}'),
        trailing: const Text('Cambiar'),
        onTap: _rangoFechas,
      );

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: AdminScaffold(
        title: 'REPORTES Y DASHBOARDS',
        body: Column(children: [
          const TabBar(tabs: [Tab(text: 'Dashboard'), Tab(text: 'Reportes'), Tab(text: 'Dinámico')]),
          if (_error != null) AdminErrorBanner(message: _error!),
          Expanded(
            child: TabBarView(children: [
              _dashboardVista(),
              ListView(padding: const EdgeInsets.all(16), children: [
                _periodo(),
                for (final e in _fijos.entries)
                  AdminCard(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(e.value.$1, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                      Text(e.value.$2, style: const TextStyle(fontSize: 12.5)),
                      Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                        TextButton(onPressed: () => _ver(e.key), child: const Text('VER')),
                        FilledButton(
                          onPressed: () => exportarReporte(context, _dio,
                              nombre: e.value.$1, ruta: '/reportes/${e.key}/exportar', params: _rango, correoInicial: _correo),
                          child: const Text('EXPORTAR'),
                        ),
                      ]),
                    ]),
                  ),
              ]),
              ListView(padding: const EdgeInsets.all(16), children: [
                if (_fuentes.isNotEmpty) ...[
                  DropdownButton<String>(
                    isExpanded: true,
                    value: _fuente,
                    items: [for (final f in _fuentes) DropdownMenuItem(value: f['clave'].toString(), child: Text(f['etiqueta'].toString()))],
                    onChanged: (v) => setState(() => _elegirFuente(v!)),
                  ),
                  ..._opcionesFuente(),
                  const SizedBox(height: 8),
                  FilledButton(onPressed: _generando ? null : _generar, child: Text(_generando ? 'GENERANDO...' : 'GENERAR REPORTE')),
                ],
                if (_tabla != null) ...[
                  const SizedBox(height: 16),
                  TablaReporteVista(tabla: _tabla!),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: () => exportarReporte(context, _dio, nombre: _tabla!['titulo'].toString(), tabla: _tabla, correoInicial: _correo),
                    icon: const Icon(Icons.ios_share),
                    label: const Text('EXPORTAR'),
                  ),
                ],
              ]),
            ]),
          ),
        ]),
      ),
    );
  }

  List<Widget> _opcionesFuente() {
    final f = _fuentes.firstWhere((x) => x['clave'] == _fuente);
    Widget chips(String titulo, List items, Set<String> elegidas, int max) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(padding: const EdgeInsets.only(top: 10, bottom: 4), child: Text(titulo, style: const TextStyle(fontWeight: FontWeight.w700))),
            Wrap(spacing: 6, runSpacing: 4, children: [
              for (final d in items.cast<Map<String, dynamic>>())
                FilterChip(
                  label: Text(d['etiqueta'].toString()),
                  selected: elegidas.contains(d['clave']),
                  onSelected: (v) => setState(() {
                    if (v && elegidas.length < max) {
                      elegidas.add(d['clave'].toString());
                    } else if (!v && elegidas.length > 1) {
                      elegidas.remove(d['clave']);
                    }
                  }),
                ),
            ]),
          ],
        );
    return [
      if (f['descripcion'] != null) Text(f['descripcion'].toString(), style: const TextStyle(fontSize: 12.5)),
      chips('Agrupar por (hasta 2)', f['dimensiones'] as List, _agrupar, 2),
      chips('Métricas (hasta 6)', f['metricas'] as List, _metricas, 6),
      if (f['con_fechas'] == true) _periodo(),
    ];
  }

  Widget _dashboardVista() {
    final d = _dashboard;
    if (d == null) return const Center(child: CircularProgressIndicator());
    Widget kpi(String titulo, String valor) => Expanded(
          child: AdminCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(titulo.toUpperCase(), style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, color: Colors.black54)),
              const SizedBox(height: 4),
              Text(valor, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            ]),
          ),
        );
    Widget serie(String titulo, List items) => AdminCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(titulo, style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            if (items.isEmpty) const Text('Sin datos.'),
            for (final i in items.cast<Map<String, dynamic>>())
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  Expanded(child: Text(i.values.first.toString())),
                  Text(i.values.skip(1).map((v) => v is num || double.tryParse('$v') != null ? (double.parse('$v')).toStringAsFixed(2) : '$v').join(' · '),
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                ]),
              ),
          ]),
        );
    return ListView(padding: const EdgeInsets.all(8), children: [
      Row(children: [kpi('Ventas hoy', '${bsTexto(d['ventas_hoy_total'])} (${d['ventas_hoy_cantidad']})'), kpi('Ventas del mes', '${bsTexto(d['ventas_mes_total'])} (${d['ventas_mes_cantidad']})')]),
      Row(children: [kpi('Ticket promedio', bsTexto(d['ticket_promedio_mes'])), kpi('Reservas activas', '${d['reservas_activas']}')]),
      Row(children: [kpi('Clientes nuevos del mes', '${d['clientes_nuevos_mes']}')]),
      serie('Ventas por método de pago', d['ventas_por_metodo'] as List),
      serie('Ventas por sucursal', d['ventas_por_sucursal'] as List),
      serie('Productos más vendidos', d['top_productos'] as List),
      serie('Ventas por día', d['ventas_por_dia'] as List),
      _pronosticoCard(),
    ]);
  }

  /// Ventas esperadas de las proximas 4 semanas (CU18, regresion) frente a
  /// las 4 ultimas reales, por semana y por sucursal.
  Widget _pronosticoCard() {
    final p = _pronostico;
    final titulo = const Text('Pronóstico de ventas · próximas 4 semanas', style: TextStyle(fontWeight: FontWeight.w800));
    if (p == null) {
      return AdminCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          titulo,
          const SizedBox(height: 6),
          Text(_pronosticoError ?? 'Calculando el pronóstico…'),
        ]),
      );
    }
    double num_(dynamic v) => double.tryParse('$v') ?? 0;
    final reales = (p['ultimas_4_semanas'] as List).map(num_).toList();
    final futuras = (p['pronostico_total'] as List).map(num_).toList();
    final etiquetas = [
      'Hace 4 sem.', 'Hace 3 sem.', 'Hace 2 sem.', 'Última sem.',
      ...(p['semanas'] as List).map((e) => e.toString()),
    ];
    final valores = [...reales, ...futuras];
    final maximo = valores.fold<double>(1, (m, v) => v > m ? v : m);
    final color = Theme.of(context).colorScheme.primary;
    final variacion = p['variacion'] == null ? null : num_(p['variacion']);
    final errorTotal = num_(p['metricas']['error_total_pct']);
    return AdminCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        titulo,
        const SizedBox(height: 4),
        Text(
          'Modelo de Machine Learning (${p['algoritmo']}). En días que no vio, acertó el total con un error de '
          '${(errorTotal * 100).toStringAsFixed(0)} %. Datos hasta el ${fechaTexto(p['datos_hasta'].toString(), hora: false)}.',
          style: const TextStyle(fontSize: 12, color: Colors.black54),
        ),
        const SizedBox(height: 10),
        for (var i = 0; i < valores.length; i++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(children: [
              SizedBox(width: 92, child: Text(etiquetas[i], style: const TextStyle(fontSize: 11.5))),
              Expanded(
                child: LayoutBuilder(
                  builder: (_, c) => Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      height: 14,
                      width: c.maxWidth * (valores[i] / maximo),
                      decoration: BoxDecoration(
                        color: i < reales.length ? color : color.withValues(alpha: 0.35),
                        border: i < reales.length ? null : Border.all(color: color),
                      ),
                    ),
                  ),
                ),
              ),
              SizedBox(width: 78, child: Text(bsTexto(valores[i].round()), textAlign: TextAlign.right, style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700))),
            ]),
          ),
        const SizedBox(height: 4),
        Text('Barras llenas: vendido · claras: pronóstico', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
        const Divider(height: 20),
        Row(children: [
          Expanded(child: Text('Próximas 4 semanas: ${bsTexto(futuras.fold<double>(0, (t, v) => t + v).round())}', style: const TextStyle(fontWeight: FontWeight.w700))),
          if (variacion != null)
            Text('${variacion > 0 ? '+' : ''}${(variacion * 100).toStringAsFixed(0)} %',
                style: TextStyle(fontWeight: FontWeight.w800, color: variacion < 0 ? const Color(0xFFA8554B) : color)),
        ]),
        const SizedBox(height: 6),
        for (final s in (p['sucursales'] as List).cast<Map<String, dynamic>>())
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              Expanded(child: Text(s['sucursal'].toString(), style: const TextStyle(fontSize: 12.5))),
              Text('${bsTexto(num_(s['total_ultimas_4']).round())} → ${bsTexto(num_(s['total_pronostico']).round())}',
                  style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700)),
            ]),
          ),
      ]),
    );
  }
}
