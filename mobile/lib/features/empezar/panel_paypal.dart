import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Panel de PayPal incrustado en la pagina (sin abrir otra ventana ni el
/// navegador): carga el enlace para aprobar la orden, el cliente inicia
/// sesion en PayPal ahi mismo y, cuando PayPal vuelve a
/// `/paypal-embed/retorno` (o `/cancelado`), avisa con el order_id aprobado
/// (o null si cancelo).
class PanelPaypal extends StatefulWidget {
  const PanelPaypal({super.key, required this.url, required this.orderId, required this.alTerminar, this.alto = 620});

  final String url;
  final String orderId;
  final ValueChanged<String?> alTerminar;
  final double alto;

  @override
  State<PanelPaypal> createState() => _PanelPaypalState();
}

class _PanelPaypalState extends State<PanelPaypal> {
  late final WebViewController _controller;
  bool _cargando = true;
  bool _terminado = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.white)
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: (pedido) {
            final uri = Uri.parse(pedido.url);
            if (uri.path.endsWith('/paypal-embed/retorno')) {
              _terminar(uri.queryParameters['token'] ?? widget.orderId);
              return NavigationDecision.prevent;
            }
            if (uri.path.endsWith('/paypal-embed/cancelado')) {
              _terminar(null);
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
          onPageStarted: (_) {
            if (mounted) setState(() => _cargando = true);
          },
          onPageFinished: (_) {
            if (mounted) setState(() => _cargando = false);
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.url));
  }

  void _terminar(String? orderId) {
    if (_terminado) return;
    _terminado = true;
    widget.alTerminar(orderId);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: widget.alto,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFDCD7D2), width: 1.5),
      ),
      child: Stack(
        children: [
          // El panel recibe sus propios desplazamientos (si no, los toma la pagina).
          WebViewWidget(
            controller: _controller,
            gestureRecognizers: {Factory<OneSequenceGestureRecognizer>(() => EagerGestureRecognizer())},
          ),
          if (_cargando) const LinearProgressIndicator(minHeight: 2, color: Color(0xFFE8806B)),
        ],
      ),
    );
  }
}
