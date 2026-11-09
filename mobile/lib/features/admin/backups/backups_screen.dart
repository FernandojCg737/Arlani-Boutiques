import 'dart:async';

import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';
import '../../auth/auth_provider.dart';
import '../widgets/admin_widgets.dart';
import '../widgets/dialogos.dart';

const _dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

/// CU26 Backups y restauracion (`/admin/backups` de la web): crear backups,
/// restaurar por secciones (merge: nunca borra lo de hoy), programarlos y ver
/// las restauraciones.
class BackupsScreen extends ConsumerStatefulWidget {
  const BackupsScreen({super.key});

  @override
  ConsumerState<BackupsScreen> createState() => _BackupsScreenState();
}

class _BackupsScreenState extends ConsumerState<BackupsScreen> {
  Map<String, dynamic>? _estado;
  List<Map<String, dynamic>> _backups = [];
  List<Map<String, dynamic>> _programas = [];
  List<Map<String, dynamic>> _restauraciones = [];
  bool _cargando = true;
  bool _importando = false;
  String? _error;
  Timer? _sondeo;

  Dio get _dio => ref.read(apiClientProvider).dio;
  Map<String, String> get _nombres => {for (final s in (_estado?['secciones'] as List? ?? [])) s['codigo'].toString(): s['nombre'].toString()};

  @override
  void initState() {
    super.initState();
    _cargar();
    // Mientras algo se esta haciendo, se refresca solo.
    _sondeo = Timer.periodic(const Duration(seconds: 5), (_) {
      if (_backups.any((b) => b['estado'] == 'en_proceso') || _restauraciones.any((r) => r['estado'] == 'en_proceso')) _cargar();
    });
  }

  @override
  void dispose() {
    _sondeo?.cancel();
    super.dispose();
  }

  Future<void> _cargar() async {
    try {
      final r = await Future.wait([
        _dio.get('/backups/estado'),
        _dio.get('/backups'),
        _dio.get('/backups/programaciones'),
        _dio.get('/backups/restauraciones'),
      ]);
      setState(() {
        _estado = r[0].data as Map<String, dynamic>;
        _backups = (r[1].data as List).cast<Map<String, dynamic>>();
        _programas = (r[2].data as List).cast<Map<String, dynamic>>();
        _restauraciones = (r[3].data as List).cast<Map<String, dynamic>>();
        _error = null;
      });
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  Future<void> _hacer(Future<void> Function() f) async {
    try {
      await f();
      await _cargar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  Future<List<String>?> _elegirSecciones(String titulo, List<String> opciones, Set<String> marcadas, {String? nota}) {
    final elegidas = {...marcadas};
    return showDialog<List<String>>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, refrescar) => AlertDialog(
          title: Text(titulo),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (nota != null) Text(nota, style: const TextStyle(fontSize: 13)),
              for (final s in opciones)
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  dense: true,
                  value: elegidas.contains(s),
                  title: Text(_nombres[s] ?? s),
                  subtitle: s == 'historial'
                      ? const Text('Se combina con el de hoy: vuelven solo las ventas, pagos y cajas que ya no existen; '
                          'lo hecho después del backup no se toca.')
                      : s == 'inventario'
                          ? const Text('El stock vuelve a la cantidad del backup.')
                          : null,
                  onChanged: (v) => refrescar(() => v == true ? elegidas.add(s) : elegidas.remove(s)),
                ),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
            FilledButton(onPressed: elegidas.isEmpty ? null : () => Navigator.pop(ctx, elegidas.toList()), child: const Text('Aceptar')),
          ],
        ),
      ),
    );
  }

  Future<void> _crear() async {
    final todas = _nombres.keys.toList();
    final s = await _elegirSecciones('Crear backup ahora', todas, todas.toSet());
    if (s != null) await _hacer(() => _dio.post('/backups', data: {'secciones': s}));
  }

  Future<void> _restaurar(Map<String, dynamic> b) async {
    final secciones = (b['secciones'] as List).cast<String>();
    final s = await _elegirSecciones('Restaurar backup #${b['numero'] ?? b['id']}', secciones, secciones.where((x) => x != 'historial').toSet(),
        nota: 'Antes de restaurar se hace un backup automático de cómo está todo ahora. Nada de lo actual se borra.');
    if (s != null) await _hacer(() => _dio.post('/backups/${b['id']}/restaurar', data: {'secciones': s}));
  }

  /// Sube el .zip de un backup descargado antes: queda como un backup mas y
  /// se ofrece restaurarlo de inmediato. El servidor solo acepta los ZIP de
  /// esta tienda, sin modificar.
  Future<void> _importar() async {
    final elegido = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['zip']);
    final archivo = elegido?.files.single;
    if (archivo == null || archivo.path == null) return;
    setState(() {
      _importando = true;
      _error = null;
    });
    try {
      final r = await _dio.post('/backups/importar',
          data: FormData.fromMap({'archivo': await MultipartFile.fromFile(archivo.path!, filename: archivo.name)}));
      await _cargar();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Backup importado como #${r.data['numero'] ?? r.data['id']}.')));
      await _restaurar(r.data as Map<String, dynamic>);
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _importando = false);
    }
  }

  String _origen(Map<String, dynamic> b) => switch (b['origen']) {
        'manual' => 'Manual',
        'programado' => 'Programado: ${b['programacion_nombre'] ?? ''}',
        'importado' => 'Importado desde un archivo',
        _ => 'Automático antes de restaurar',
      };

  Future<void> _programar([Map<String, dynamic>? p]) async {
    final ok = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => _Programacion(dio: _dio, programa: p, secciones: _nombres),
    ));
    if (ok == true) _cargar();
  }

  String _cuando(Map<String, dynamic> p) {
    final h = p['hora'].toString().substring(0, 5);
    return switch (p['frecuencia']) {
      'una_vez' => 'Una vez, el ${fechaTexto(p['fecha'], hora: false)} a las $h',
      'diaria' => 'Todos los días a las $h',
      'semanal' => 'Cada ${_dias[p['dia_semana'] as int]} a las $h',
      _ => 'El día ${p['dia_mes']} de cada mes a las $h',
    };
  }

  @override
  Widget build(BuildContext context) {
    final disponible = _estado?['disponible'] == true;
    return DefaultTabController(
      length: 3,
      child: AdminScaffold(
        title: 'BACKUPS Y RESTAURACION',
        floatingActionButton: disponible ? FloatingActionButton.extended(onPressed: _crear, icon: const Icon(Icons.backup), label: const Text('Backup')) : null,
        body: _cargando
            ? const Center(child: CircularProgressIndicator())
            : Column(children: [
                if (_error != null) AdminErrorBanner(message: _error!),
                if (!disponible)
                  Container(
                    padding: const EdgeInsets.all(12),
                    color: const Color(0xFFFFF4E0),
                    child: Text('Los backups son de los planes Básico y Profesional (tu plan: ${_estado?['plan'] ?? 'actual'}).'),
                  ),
                TabBar(tabs: [
                  Tab(text: 'Backups (${_backups.length})'),
                  Tab(text: 'Programación (${_programas.length})'),
                  Tab(text: 'Restauraciones'),
                ]),
                Expanded(
                  child: TabBarView(children: [
                    RefreshIndicator(
                      onRefresh: _cargar,
                      child: ListView(padding: const EdgeInsets.only(bottom: 90), children: [
                        if (disponible)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                            child: OutlinedButton.icon(
                              onPressed: _importando ? null : _importar,
                              icon: _importando
                                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                                  : const Icon(Icons.upload_file),
                              label: Text(_importando ? 'IMPORTANDO…' : 'IMPORTAR BACKUP (.ZIP)'),
                            ),
                          ),
                        if (_backups.isEmpty) const Padding(padding: EdgeInsets.all(24), child: Text('Todavía no hay backups.')),
                        for (final b in _backups)
                          AdminCard(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Row(children: [
                                Expanded(child: Text('#${b['numero'] ?? b['id']} · ${fechaTexto(b['creado_en'])}', style: const TextStyle(fontWeight: FontWeight.w800))),
                                NeutralBadge(b['estado'] == 'en_proceso' ? 'EN PROCESO' : b['estado'] == 'completado' ? 'COMPLETADO' : 'FALLÓ'),
                              ]),
                              Text('${_origen(b)}${b['creado_por'] != null ? ' · ${b['creado_por']}' : ''}', style: const TextStyle(fontSize: 12)),
                              Text((b['secciones'] as List).map((s) => _nombres[s] ?? s).join(' · '), style: const TextStyle(fontSize: 12)),
                              if (b['tamano_bytes'] != null)
                                Text('${((b['tamano_bytes'] as num) / 1048576).toStringAsFixed(1)} MB · ${b['imagenes'] ?? 0} imágenes',
                                    style: const TextStyle(fontSize: 12)),
                              if (b['error'] != null) Text(b['error'].toString(), style: const TextStyle(color: Color(0xFFB3261E), fontSize: 12)),
                              if (b['estado'] != 'en_proceso')
                                Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                                  if (b['estado'] == 'completado' && disponible)
                                    TextButton(onPressed: () => _restaurar(b), child: const Text('RESTAURAR')),
                                  TextButton(
                                    onPressed: () async {
                                      if (await confirmarDialogo(context, '¿Borrar el backup #${b['numero'] ?? b['id']}?', si: 'Borrar', peligro: true)) {
                                        await _hacer(() => _dio.delete('/backups/${b['id']}'));
                                      }
                                    },
                                    child: const Text('BORRAR', style: TextStyle(color: Color(0xFFB3261E))),
                                  ),
                                ]),
                            ]),
                          ),
                      ]),
                    ),
                    ListView(padding: const EdgeInsets.only(bottom: 90), children: [
                      const Padding(
                        padding: EdgeInsets.all(16),
                        child: Text('Se hacen solos en la fecha y hora que elijas (hora de Bolivia), una vez o cada día, semana o mes. '
                            'Cada programación guarda sus últimos backups y borra los más viejos.'),
                      ),
                      if (disponible)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: OutlinedButton(onPressed: () => _programar(), child: const Text('NUEVA PROGRAMACIÓN')),
                        ),
                      for (final p in _programas)
                        AdminCard(
                          child: InkWell(
                            onTap: disponible ? () => _programar(p) : null,
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Row(children: [
                                Expanded(child: Text(p['nombre'].toString(), style: const TextStyle(fontWeight: FontWeight.w800))),
                                NeutralBadge(p['activa'] == true ? 'ACTIVA' : 'PAUSADA'),
                              ]),
                              Text(_cuando(p)),
                              if (p['activa'] == true && p['proxima_ejecucion'] != null) Text('Próximo: ${fechaTexto(p['proxima_ejecucion'])}'),
                              Text('Guarda los últimos ${p['retener']} · tiene ${p['backups']}', style: const TextStyle(fontSize: 12)),
                            ]),
                          ),
                        ),
                    ]),
                    ListView(children: [
                      if (_restauraciones.isEmpty) const Padding(padding: EdgeInsets.all(24), child: Text('Todavía no se restauró ningún backup.')),
                      for (final r in _restauraciones)
                        AdminCard(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Row(children: [
                              Expanded(child: Text(fechaTexto(r['creado_en']), style: const TextStyle(fontWeight: FontWeight.w800))),
                              NeutralBadge(r['estado'] == 'en_proceso' ? 'EN PROCESO' : r['estado'] == 'completada' ? 'COMPLETADA' : 'FALLÓ'),
                            ]),
                            Text('Desde el backup #${r['backup_numero'] ?? r['backup_id'] ?? '—'} · ${r['hecho_por'] ?? ''}', style: const TextStyle(fontSize: 12)),
                            Text((r['secciones'] as List).map((s) => _nombres[s] ?? s).join(' · '), style: const TextStyle(fontSize: 12)),
                            if (r['resumen'] != null) Text(_totales(r['resumen'] as Map<String, dynamic>), style: const TextStyle(fontSize: 12)),
                            if (r['backup_previo_id'] != null) Text('Para volver atrás: backup #${r['backup_previo_numero'] ?? r['backup_previo_id']}', style: const TextStyle(fontSize: 12)),
                            if (r['error'] != null) Text(r['error'].toString(), style: const TextStyle(color: Color(0xFFB3261E), fontSize: 12)),
                          ]),
                        ),
                    ]),
                  ]),
                ),
              ]),
      ),
    );
  }

  String _totales(Map<String, dynamic> resumen) {
    var volvieron = 0, actualizadas = 0, omitidas = 0;
    for (final t in (resumen['tablas'] as Map? ?? {}).values) {
      volvieron += (t['volvieron'] as num).toInt();
      actualizadas += (t['actualizadas'] as num).toInt();
      omitidas += (t['omitidas'] as num).toInt();
    }
    return 'Volvieron $volvieron · se restauraron $actualizadas · no pudieron volver $omitidas · ${resumen['imagenes'] ?? 0} imágenes';
  }
}

class _Programacion extends StatefulWidget {
  const _Programacion({required this.dio, required this.programa, required this.secciones});
  final Dio dio;
  final Map<String, dynamic>? programa;
  final Map<String, String> secciones;

  @override
  State<_Programacion> createState() => _ProgramacionState();
}

class _ProgramacionState extends State<_Programacion> {
  late final _nombre = TextEditingController(text: widget.programa?['nombre']?.toString() ?? 'Backup diario');
  late String _frecuencia = widget.programa?['frecuencia']?.toString() ?? 'diaria';
  late TimeOfDay _hora = _leerHora(widget.programa?['hora']?.toString() ?? '03:00');
  late DateTime? _fecha = widget.programa?['fecha'] == null ? null : DateTime.parse(widget.programa!['fecha'].toString());
  late int _diaSemana = (widget.programa?['dia_semana'] as int?) ?? 0;
  late int _diaMes = (widget.programa?['dia_mes'] as int?) ?? 1;
  late int _retener = (widget.programa?['retener'] as int?) ?? 10;
  late bool _activa = widget.programa?['activa'] != false;
  late final Set<String> _secciones = {...((widget.programa?['secciones'] as List?)?.cast<String>() ?? widget.secciones.keys)};
  String? _error;

  static TimeOfDay _leerHora(String s) => TimeOfDay(hour: int.parse(s.substring(0, 2)), minute: int.parse(s.substring(3, 5)));

  Future<void> _guardar() async {
    String dos(int n) => n.toString().padLeft(2, '0');
    final cuerpo = {
      'nombre': _nombre.text.trim(),
      'frecuencia': _frecuencia,
      'hora': '${dos(_hora.hour)}:${dos(_hora.minute)}',
      'fecha': _frecuencia == 'una_vez' && _fecha != null ? '${_fecha!.year}-${dos(_fecha!.month)}-${dos(_fecha!.day)}' : null,
      'dia_semana': _frecuencia == 'semanal' ? _diaSemana : null,
      'dia_mes': _frecuencia == 'mensual' ? _diaMes : null,
      'secciones': _secciones.toList(),
      'retener': _retener,
      'activa': _activa,
    };
    try {
      final id = widget.programa?['id'];
      if (id == null) {
        await widget.dio.post('/backups/programaciones', data: cuerpo);
      } else {
        await widget.dio.put('/backups/programaciones/$id', data: cuerpo);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: widget.programa == null ? 'NUEVA PROGRAMACION' : 'EDITAR PROGRAMACION',
      actions: [
        if (widget.programa != null)
          IconButton(
            icon: const Icon(Icons.delete_outline),
            onPressed: () async {
              if (!await confirmarDialogo(context, '¿Borrar esta programación? Los backups que ya hizo se conservan.', si: 'Borrar', peligro: true)) return;
              await widget.dio.delete('/backups/programaciones/${widget.programa!['id']}');
              if (context.mounted) Navigator.pop(context, true);
            },
          ),
      ],
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (_error != null) AdminErrorBanner(message: _error!),
        TextField(controller: _nombre, decoration: const InputDecoration(labelText: 'Nombre')),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          value: _frecuencia,
          decoration: const InputDecoration(labelText: 'Frecuencia'),
          items: const [
            DropdownMenuItem(value: 'una_vez', child: Text('Una vez')),
            DropdownMenuItem(value: 'diaria', child: Text('Todos los días')),
            DropdownMenuItem(value: 'semanal', child: Text('Cada semana')),
            DropdownMenuItem(value: 'mensual', child: Text('Cada mes')),
          ],
          onChanged: (v) => setState(() => _frecuencia = v ?? _frecuencia),
        ),
        if (_frecuencia == 'una_vez')
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(_fecha == null ? 'Elegir fecha' : 'Fecha: ${fechaTexto(_fecha!.toIso8601String().substring(0, 10), hora: false)}'),
            trailing: const Icon(Icons.calendar_today),
            onTap: () async {
              final f = await showDatePicker(context: context, firstDate: DateTime.now(), lastDate: DateTime.now().add(const Duration(days: 365)));
              if (f != null) setState(() => _fecha = f);
            },
          ),
        if (_frecuencia == 'semanal')
          DropdownButtonFormField<int>(
            value: _diaSemana,
            decoration: const InputDecoration(labelText: 'Día'),
            items: [for (var i = 0; i < 7; i++) DropdownMenuItem(value: i, child: Text(_dias[i]))],
            onChanged: (v) => setState(() => _diaSemana = v ?? 0),
          ),
        if (_frecuencia == 'mensual')
          DropdownButtonFormField<int>(
            value: _diaMes,
            decoration: const InputDecoration(labelText: 'Día del mes', helperText: 'Si el mes no tiene ese día, se hace el último.'),
            items: [for (var i = 1; i <= 31; i++) DropdownMenuItem(value: i, child: Text('$i'))],
            onChanged: (v) => setState(() => _diaMes = v ?? 1),
          ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('Hora (Bolivia): ${_hora.format(context)}'),
          trailing: const Icon(Icons.schedule),
          onTap: () async {
            final h = await showTimePicker(context: context, initialTime: _hora);
            if (h != null) setState(() => _hora = h);
          },
        ),
        const Text('Qué respaldar', style: TextStyle(fontWeight: FontWeight.w700)),
        for (final s in widget.secciones.entries)
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            value: _secciones.contains(s.key),
            title: Text(s.value),
            onChanged: (v) => setState(() => v == true ? _secciones.add(s.key) : _secciones.remove(s.key)),
          ),
        DropdownButtonFormField<int>(
          value: _retener,
          decoration: const InputDecoration(
            labelText: 'Cuántos backups guardar',
            helperText: 'Al hacerse uno nuevo, se borra solo el más viejo de esta programación.',
          ),
          items: [for (final n in ({3, 5, 7, 10, 12, 15, 30, 60, _retener}.toList()..sort())) DropdownMenuItem(value: n, child: Text('$n'))],
          onChanged: (v) => setState(() => _retener = v ?? 10),
        ),
        SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Activa'), value: _activa, onChanged: (v) => setState(() => _activa = v)),
        FilledButton(style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)), onPressed: _guardar, child: const Text('GUARDAR')),
      ]),
    );
  }
}
