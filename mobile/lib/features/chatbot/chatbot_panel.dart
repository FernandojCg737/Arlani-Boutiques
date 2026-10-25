import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:speech_to_text/speech_to_text.dart';

import '../../models/chat_mensaje.dart';
import 'chatbot_provider.dart';

/// Panel flotante del asistente universal (`.chatbot-panel` de la web): se
/// abre sobre la portada al tocar la burbuja, con su encabezado azul noche,
/// los mensajes, el microfono y "Enviar". Responde en voz alta si esta activo.
class ChatbotPanel extends ConsumerStatefulWidget {
  const ChatbotPanel({super.key});

  static const azulNoche = Color(0xFF1F2A44);
  static const oro = Color(0xFFF2B8A6);

  @override
  ConsumerState<ChatbotPanel> createState() => _ChatbotPanelState();
}

class _ChatbotPanelState extends ConsumerState<ChatbotPanel> {
  final _texto = TextEditingController();
  final _scroll = ScrollController();
  final _speech = SpeechToText();
  final _tts = FlutterTts();

  bool _vozActiva = true;
  bool _escuchando = false;
  bool _speechDisponible = false;

  @override
  void initState() {
    super.initState();
    ref.read(chatbotUniversalProvider.notifier).cargar().whenComplete(_alFinal);
    _speech.initialize().then((ok) {
      if (mounted) setState(() => _speechDisponible = ok);
    });
    _tts.setLanguage('es-US');
    _tts.setSpeechRate(0.48);
    _texto.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _texto.dispose();
    _scroll.dispose();
    _speech.stop();
    _tts.stop();
    super.dispose();
  }

  void _alFinal() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
    });
  }

  Future<void> _escuchar() async {
    if (!_speechDisponible) return;
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
          setState(() => _escuchando = false);
          _enviar();
        }
      },
      listenOptions: SpeechListenOptions(localeId: 'es_BO'),
    );
  }

  Future<void> _enviar() async {
    final texto = _texto.text;
    if (texto.trim().isEmpty || ref.read(chatbotUniversalProvider).enviando) return;
    _texto.clear();
    final future = ref.read(chatbotUniversalProvider.notifier).enviar(texto);
    _alFinal();
    final respuesta = await future;
    _alFinal();
    if (respuesta != null && _vozActiva) await _tts.speak(respuesta.mensaje);
  }

  @override
  Widget build(BuildContext context) {
    final estado = ref.watch(chatbotUniversalProvider);
    final puedeEnviar = _texto.text.trim().isNotEmpty && !estado.enviando;

    return Material(
      color: Colors.white,
      elevation: 12,
      shadowColor: Colors.black.withValues(alpha: 0.4),
      shape: const Border.fromBorderSide(BorderSide(color: Color(0xFFEEEEEE))),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Container(
            color: ChatbotPanel.azulNoche,
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('ASISTENTE ARLANI BOUTIQUES',
                          style: GoogleFonts.inter(color: ChatbotPanel.oro, fontSize: 13, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 2),
                      Text('Prendas de todas las tiendas, planes y cómo crear tu boutique',
                          style: GoogleFonts.inter(color: Colors.white.withValues(alpha: 0.7), fontSize: 11)),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                Material(
                  color: Colors.white.withValues(alpha: _vozActiva ? 0.25 : 0.12),
                  child: InkWell(
                    onTap: () {
                      setState(() => _vozActiva = !_vozActiva);
                      if (!_vozActiva) _tts.stop();
                    },
                    child: SizedBox(
                      width: 30,
                      height: 30,
                      child: Icon(
                        _vozActiva ? Icons.volume_up_outlined : Icons.volume_off_outlined,
                        size: 16,
                        color: Colors.white,
                        semanticLabel: _vozActiva ? 'Silenciar respuestas' : 'Activar respuestas habladas',
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Container(
              color: const Color(0xFFF7F7F5),
              child: estado.mensajes.isEmpty && !estado.enviando
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(
                          '¡Hola! Pregúntame por prendas de todas las tiendas (precios como «menos de 200 Bs», stock, qué '
                          'tienda vende qué) o, si tienes una boutique, por los planes y cómo crear la tuya en Arlani.',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF999999)),
                        ),
                      ),
                    )
                  : ListView.separated(
                      controller: _scroll,
                      padding: const EdgeInsets.all(16),
                      itemCount: estado.mensajes.length + (estado.enviando ? 1 : 0),
                      separatorBuilder: (_, _) => const SizedBox(height: 10),
                      itemBuilder: (context, i) =>
                          i == estado.mensajes.length ? const _Escribiendo() : _Burbuja(mensaje: estado.mensajes[i]),
                    ),
            ),
          ),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: const BoxDecoration(
              color: Colors.white,
              border: Border(top: BorderSide(color: Color(0xFFEEEEEE))),
            ),
            child: Row(
              children: [
                if (_speechDisponible) ...[
                  Material(
                    color: _escuchando ? const Color(0xFFB3261E) : Colors.white,
                    shape: Border.all(color: _escuchando ? const Color(0xFFB3261E) : const Color(0xFFDDDDDD)),
                    child: InkWell(
                      onTap: estado.enviando ? null : _escuchar,
                      child: SizedBox(
                        width: 34,
                        height: 34,
                        child: Icon(Icons.mic_none, size: 18,
                            color: _escuchando ? Colors.white : ChatbotPanel.azulNoche, semanticLabel: 'Preguntar por voz'),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                ],
                Expanded(
                  child: SizedBox(
                    height: 34,
                    child: TextField(
                      controller: _texto,
                      enabled: !estado.enviando,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _enviar(),
                      style: GoogleFonts.inter(fontSize: 13, color: ChatbotPanel.azulNoche),
                      decoration: InputDecoration(
                        hintText: _escuchando ? 'Escuchando...' : 'Escribi tu pregunta...',
                        hintStyle: GoogleFonts.inter(fontSize: 13, color: const Color(0xFF999999)),
                        isDense: true,
                        filled: false,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                        border: const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: Color(0xFFDDDDDD))),
                        enabledBorder:
                            const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: Color(0xFFDDDDDD))),
                        focusedBorder:
                            const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: ChatbotPanel.azulNoche)),
                        disabledBorder:
                            const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: Color(0xFFDDDDDD))),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Opacity(
                  opacity: puedeEnviar ? 1 : 0.45,
                  child: Material(
                    color: ChatbotPanel.azulNoche,
                    child: InkWell(
                      onTap: puedeEnviar ? _enviar : null,
                      child: Container(
                        height: 34,
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                        alignment: Alignment.center,
                        child: Text('ENVIAR',
                            style: GoogleFonts.inter(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.44)),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Burbuja extends StatelessWidget {
  const _Burbuja({required this.mensaje});

  final ChatMensaje mensaje;

  @override
  Widget build(BuildContext context) {
    final bot = mensaje.esBot;
    final hora = TimeOfDay.fromDateTime(mensaje.fecha.toLocal()).format(context);
    return Align(
      alignment: bot ? Alignment.centerLeft : Alignment.centerRight,
      child: FractionallySizedBox(
        widthFactor: 0.85,
        alignment: bot ? Alignment.centerLeft : Alignment.centerRight,
        child: Align(
          alignment: bot ? Alignment.centerLeft : Alignment.centerRight,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: bot ? Colors.white : ChatbotPanel.azulNoche,
              border: bot ? Border.all(color: const Color(0xFFEEEEEE)) : null,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(mensaje.mensaje,
                    style: GoogleFonts.inter(fontSize: 13, height: 1.4, color: bot ? ChatbotPanel.azulNoche : Colors.white)),
                const SizedBox(height: 4),
                Text(hora,
                    style: GoogleFonts.inter(fontSize: 10, color: bot ? const Color(0xFF999999) : Colors.white.withValues(alpha: 0.6))),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Escribiendo extends StatelessWidget {
  const _Escribiendo();

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(color: Colors.white, border: Border.all(color: const Color(0xFFEEEEEE))),
        child: const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
      ),
    );
  }
}
