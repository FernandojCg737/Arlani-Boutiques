import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../../core/api_client.dart';
import '../../auth/auth_provider.dart';
import '../widgets/admin_widgets.dart';
import 'reportes_comun.dart';

/// CU25 Reportes por voz con IA (`/admin/reporte-voz` de la web, plan
/// Profesional): se pide el reporte hablando o escribiendo; la IA reconoce
/// cual es y sus filtros, y responde la tabla, un resumen en palabras (que se
/// lee en voz alta) y se exporta igual que los demas reportes.
class ReporteVozScreen extends ConsumerStatefulWidget {
  const ReporteVozScreen({super.key});

  @override
  ConsumerState<ReporteVozScreen> createState() => _ReporteVozScreenState();
}

class _ReporteVozScreenState extends ConsumerState<ReporteVozScreen> {
  final _speech = SpeechToText();
  final _tts = FlutterTts();
  final _texto = TextEditingController();
  Map<String, dynamic>? _estado;
  Map<String, dynamic>? _respuesta;
  bool _speechOk = false;
  bool _escuchando = false;
  bool _porVoz = false;
  bool _generando = false;
  bool _leer = true;
  String? _error;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _tts.setLanguage('es-US');
    _speech.initialize().then((ok) => mounted ? setState(() => _speechOk = ok) : null);
    _dio.get('/reportes-voz/estado').then((r) => mounted ? setState(() => _estado = r.data as Map<String, dynamic>) : null,
        onError: (e) => mounted ? setState(() => _error = extractErrorMessage(e)) : null);
  }

  @override
  void dispose() {
    _speech.stop();
    _tts.stop();
    _texto.dispose();
    super.dispose();
  }

  Future<void> _escuchar() async {
    if (_escuchando) {
      await _speech.stop();
      setState(() => _escuchando = false);
      return;
    }
    setState(() => _escuchando = true);
    await _speech.listen(
      onResult: (r) {
        _texto.text = r.recognizedWords;
        if (r.finalResult) {
          setState(() {
            _escuchando = false;
            _porVoz = true;
          });
          _generar();
        }
      },
      listenOptions: SpeechListenOptions(localeId: 'es_BO'),
    );
  }

  Future<void> _generar([String? sugerencia]) async {
    if (sugerencia != null) _texto.text = sugerencia;
    final texto = _texto.text.trim();
    if (texto.length < 2 || _generando) return;
    setState(() {
      _generando = true;
      _error = null;
    });
    try {
      final r = await _dio.post('/reportes-voz', data: {'texto': texto, 'por_voz': _porVoz});
      final d = r.data as Map<String, dynamic>;
      setState(() => _respuesta = d);
      final decir = d['entendido'] == true ? d['narrativa'] : d['mensaje'];
      if (_leer && decir != null) await _tts.speak(decir.toString());
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      _porVoz = false;
      if (mounted) setState(() => _generando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final estado = _estado;
    final r = _respuesta;
    return AdminScaffold(
      title: 'REPORTES POR VOZ (IA)',
      actions: [
        IconButton(
          tooltip: _leer ? 'No leer en voz alta' : 'Leer en voz alta',
          icon: Icon(_leer ? Icons.volume_up : Icons.volume_off),
          onPressed: () {
            if (_leer) _tts.stop();
            setState(() => _leer = !_leer);
          },
        ),
      ],
      body: estado == null
          ? (_error != null ? AdminErrorBanner(message: _error!) : const Center(child: CircularProgressIndicator()))
          : estado['disponible'] != true
              ? Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text('Los reportes con IA son del plan Profesional (tu tienda tiene el plan ${estado['plan'] ?? 'actual'}). '
                      'Los reportes normales están en Reportes y dashboards.'),
                )
              : ListView(padding: const EdgeInsets.all(16), children: [
                  const Text('Pide el reporte hablando o escribiendo, por ejemplo: «ventas de este mes por sucursal».'),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(
                      child: TextField(
                        controller: _texto,
                        textInputAction: TextInputAction.search,
                        onSubmitted: (_) => _generar(),
                        decoration: const InputDecoration(hintText: '¿Qué reporte necesitas?'),
                      ),
                    ),
                    const SizedBox(width: 6),
                    IconButton.filled(
                      tooltip: _escuchando ? 'Detener' : 'Hablar',
                      onPressed: _speechOk ? _escuchar : null,
                      icon: Icon(_escuchando ? Icons.stop : Icons.mic),
                    ),
                    IconButton(onPressed: _generando ? null : () => _generar(), icon: const Icon(Icons.send)),
                  ]),
                  if (_escuchando) const Padding(padding: EdgeInsets.only(top: 6), child: Text('Escuchando…', style: TextStyle(color: Colors.red))),
                  const SizedBox(height: 10),
                  Wrap(spacing: 6, runSpacing: 6, children: [
                    for (final s in (estado['sugerencias'] as List? ?? []).take(6))
                      ActionChip(label: Text(s.toString()), onPressed: () => _generar(s.toString())),
                  ]),
                  if (_error != null) AdminErrorBanner(message: _error!),
                  if (_generando) const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator())),
                  if (r != null && !_generando) ...[
                    const SizedBox(height: 16),
                    if (r['entendido'] != true)
                      Text(r['mensaje'].toString())
                    else ...[
                      Wrap(spacing: 6, runSpacing: 4, children: [
                        Chip(label: Text(r['interpretacion']['reporte'].toString())),
                        for (final f in (r['interpretacion']['filtros'] as List? ?? [])) Chip(label: Text(f.toString())),
                      ]),
                      if (r['narrativa'] != null)
                        Container(
                          margin: const EdgeInsets.symmetric(vertical: 10),
                          padding: const EdgeInsets.all(12),
                          color: const Color(0xFFF4F1EE),
                          child: Text(r['narrativa'].toString()),
                        ),
                      TablaReporteVista(tabla: r['tabla'] as Map<String, dynamic>),
                      const SizedBox(height: 8),
                      OutlinedButton.icon(
                        onPressed: () => exportarReporte(context, _dio,
                            nombre: r['tabla']['titulo'].toString(), tabla: r['tabla'] as Map<String, dynamic>,
                            correoInicial: ref.read(authProvider).usuario?.email),
                        icon: const Icon(Icons.ios_share),
                        label: const Text('EXPORTAR'),
                      ),
                    ],
                  ],
                ]),
    );
  }
}
