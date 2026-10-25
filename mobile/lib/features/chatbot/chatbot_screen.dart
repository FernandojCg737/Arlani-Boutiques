import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../core/theme.dart';
import '../../models/chat_mensaje.dart';
import 'chatbot_provider.dart';

/// CU19, lado cliente: chat con el asistente virtual. El reconocimiento de
/// voz (dictar la pregunta) y la sintesis de voz (que el bot conteste
/// hablado) son el equivalente nativo del Web Speech API que usa la web
/// (`speech_to_text` / `flutter_tts`, ya que ese API no existe en Flutter).
class ChatbotScreen extends ConsumerStatefulWidget {
  const ChatbotScreen({super.key, this.universal = false});

  /// El asistente de Arlani Boutiques (portada): todas las tiendas, planes y
  /// como crear una boutique; lo puede usar cualquiera, con o sin sesion.
  final bool universal;

  @override
  ConsumerState<ChatbotScreen> createState() => _ChatbotScreenState();
}

class _ChatbotScreenState extends ConsumerState<ChatbotScreen> {
  final _textoCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final _speech = SpeechToText();
  final _tts = FlutterTts();

  bool _cargando = true;
  bool _vozActiva = true;
  bool _escuchando = false;
  bool _speechDisponible = false;

  StateNotifierProvider<ChatbotNotifier, ChatbotState> get _chat =>
      widget.universal ? chatbotUniversalProvider : chatbotProvider;

  @override
  void initState() {
    super.initState();
    ref.read(_chat.notifier).cargar().whenComplete(() {
      if (mounted) {
        setState(() => _cargando = false);
        _scrollAlFinal();
      }
    });
    _speech.initialize().then((disponible) {
      if (mounted) setState(() => _speechDisponible = disponible);
    });
    _tts.setLanguage('es-US');
    _tts.setSpeechRate(0.48);
  }

  @override
  void dispose() {
    _textoCtrl.dispose();
    _scrollCtrl.dispose();
    _speech.stop();
    _tts.stop();
    super.dispose();
  }

  void _scrollAlFinal() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollCtrl.hasClients) return;
      _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
    });
  }

  void _toggleVoz() {
    setState(() => _vozActiva = !_vozActiva);
    if (!_vozActiva) _tts.stop();
  }

  Future<void> _escuchar() async {
    if (!_speechDisponible || _escuchando) return;
    setState(() => _escuchando = true);
    await _speech.listen(
      onResult: (result) {
        _textoCtrl.text = result.recognizedWords;
        if (result.finalResult) {
          setState(() => _escuchando = false);
          _enviar();
        }
      },
      listenOptions: SpeechListenOptions(localeId: 'es_BO'),
    );
  }

  Future<void> _enviar() async {
    final texto = _textoCtrl.text;
    if (texto.trim().isEmpty || ref.read(_chat).enviando) return;
    _textoCtrl.clear();

    final respuesta = await ref.read(_chat.notifier).enviar(texto);
    _scrollAlFinal();
    if (respuesta != null && _vozActiva) {
      await _tts.speak(respuesta.mensaje);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(_chat);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.universal ? 'ASISTENTE ARLANI' : 'ASISTENTE VIRTUAL'),
        actions: [
          IconButton(
            icon: Icon(_vozActiva ? Icons.volume_up_outlined : Icons.volume_off_outlined),
            onPressed: _toggleVoz,
            tooltip: _vozActiva ? 'Silenciar respuestas' : 'Activar respuestas habladas',
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: _cargando
                  ? const Center(child: CircularProgressIndicator())
                  : state.mensajes.isEmpty
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Text(
                              widget.universal
                                  ? 'Hola! Preguntame por prendas de todas las tiendas, los planes o cómo crear tu boutique.'
                                  : 'Hola! Preguntame sobre el stock de un producto, precios, sucursales o metodos de pago.',
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: AppColors.grayText),
                            ),
                          ),
                        )
                      : ListView.builder(
                          controller: _scrollCtrl,
                          padding: const EdgeInsets.all(16),
                          itemCount: state.mensajes.length + (state.enviando ? 1 : 0),
                          itemBuilder: (context, i) {
                            if (i == state.mensajes.length) return const _EscribiendoBubble();
                            return _MensajeBubble(mensaje: state.mensajes[i]);
                          },
                        ),
            ),
            Padding(
              padding: const EdgeInsets.all(10),
              child: Row(
                children: [
                  if (_speechDisponible)
                    IconButton(
                      onPressed: _escuchando ? () => _speech.stop() : _escuchar,
                      icon: Icon(Icons.mic, color: _escuchando ? AppColors.danger : AppColors.brandDark),
                    ),
                  Expanded(
                    child: TextField(
                      controller: _textoCtrl,
                      decoration: InputDecoration(hintText: _escuchando ? 'Escuchando...' : 'Escribi tu pregunta...'),
                      onSubmitted: (_) => _enviar(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    onPressed: state.enviando ? null : _enviar,
                    icon: const Icon(Icons.send, color: AppColors.brandDark),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MensajeBubble extends StatelessWidget {
  const _MensajeBubble({required this.mensaje});

  final ChatMensaje mensaje;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: mensaje.esBot ? Alignment.centerLeft : Alignment.centerRight,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: mensaje.esBot ? Colors.white : AppColors.brandDark,
          border: mensaje.esBot ? Border.all(color: AppColors.grayBorderLight) : null,
        ),
        child: Text(
          mensaje.mensaje,
          style: TextStyle(fontSize: 13, color: mensaje.esBot ? AppColors.brandDark : Colors.white),
        ),
      ),
    );
  }
}

class _EscribiendoBubble extends StatelessWidget {
  const _EscribiendoBubble();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(color: Colors.white, border: Border.all(color: AppColors.grayBorderLight)),
        child: const SizedBox(width: 24, height: 12, child: Center(child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)))),
      ),
    );
  }
}
