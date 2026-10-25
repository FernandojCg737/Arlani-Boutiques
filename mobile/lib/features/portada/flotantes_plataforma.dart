import 'package:flutter/material.dart';

import '../../widgets/whatsapp_float_button.dart';
import '../chatbot/chatbot_panel.dart';
import 'estilo_plataforma.dart';

/// Botones flotantes de las paginas de la plataforma (portada y catalogo
/// universal): el asistente universal a la izquierda, que abre su panel, y
/// WhatsApp a la derecha. Aparecen cuando el hero sale de la pantalla, o
/// siempre que el panel este abierto. Va como ultimo hijo del Stack de la
/// pagina; las zonas vacias dejan pasar los toques.
class FlotantesPlataforma extends StatefulWidget {
  const FlotantesPlataforma({super.key, required this.visible});

  final bool visible;

  @override
  State<FlotantesPlataforma> createState() => _FlotantesPlataformaState();
}

class _FlotantesPlataformaState extends State<FlotantesPlataforma> {
  bool _chatAbierto = false;

  @override
  Widget build(BuildContext context) {
    final abajo = MediaQuery.paddingOf(context).bottom;
    final alto = MediaQuery.sizeOf(context).height;

    return Positioned.fill(
      child: Stack(
        children: [
          if (_chatAbierto)
            Positioned(
              left: 16,
              right: 16,
              bottom: 84 + abajo,
              height: (alto * 0.7).clamp(0.0, 520.0),
              child: Align(
                alignment: Alignment.bottomLeft,
                child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 360), child: const ChatbotPanel()),
              ),
            ),
          Positioned(
            left: 20,
            bottom: 20 + abajo,
            child: _Aparece(
              visible: widget.visible || _chatAbierto,
              child: _BotonAsistente(abierto: _chatAbierto, onTap: () => setState(() => _chatAbierto = !_chatAbierto)),
            ),
          ),
          Positioned(
            right: 16,
            bottom: 16 + abajo,
            child: _Aparece(visible: widget.visible, child: const WhatsappFloatButton()),
          ),
        ],
      ),
    );
  }
}

class _Aparece extends StatelessWidget {
  const _Aparece({required this.visible, required this.child});

  final bool visible;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedOpacity(opacity: visible ? 1 : 0, duration: const Duration(milliseconds: 200), child: child),
    );
  }
}

/// Burbuja del asistente universal: coral oscuro (`.chatbot--universal`);
/// con el panel abierto se vuelve una X.
class _BotonAsistente extends StatelessWidget {
  const _BotonAsistente({required this.abierto, required this.onTap});

  final bool abierto;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Plataforma.coralOscuro,
      shape: const CircleBorder(),
      elevation: 6,
      shadowColor: Colors.black.withValues(alpha: 0.5),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: SizedBox(
          width: 54,
          height: 54,
          child: Icon(
            abierto ? Icons.close : Icons.chat_bubble_outline,
            color: Colors.white,
            semanticLabel: abierto ? 'Cerrar asistente' : 'Asistente Arlani Boutiques',
          ),
        ),
      ),
    );
  }
}
