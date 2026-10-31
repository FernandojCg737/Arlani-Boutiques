import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Pago con PayPal dentro de la app (sin abrir el navegador): carga el enlace
/// para aprobar la orden y, cuando PayPal vuelve a `/paypal-embed/retorno`
/// (o `/cancelado`), cierra devolviendo el order_id aprobado (o null).
class PaypalAprobarScreen extends StatefulWidget {
  const PaypalAprobarScreen({super.key, required this.url, required this.orderId});

  final String url;
  final String orderId;

  @override
  State<PaypalAprobarScreen> createState() => _PaypalAprobarScreenState();
}

class _PaypalAprobarScreenState extends State<PaypalAprobarScreen> {
  late final WebViewController _controller;
  bool _cargando = true;
  bool _cerrado = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onNavigationRequest: (pedido) {
            final uri = Uri.parse(pedido.url);
            if (uri.path.endsWith('/paypal-embed/retorno')) {
              _cerrar(uri.queryParameters['token'] ?? widget.orderId);
              return NavigationDecision.prevent;
            }
            if (uri.path.endsWith('/paypal-embed/cancelado')) {
              _cerrar(null);
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
          onPageFinished: (_) {
            if (mounted) setState(() => _cargando = false);
          },
        ),
      )
      ..loadRequest(Uri.parse(widget.url));
  }

  void _cerrar(String? orderId) {
    if (_cerrado || !mounted) return;
    _cerrado = true;
    Navigator.of(context).pop(orderId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF121A2C),
        elevation: 0,
        title: Text('Pagar con PayPal', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w700)),
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Cancelar el pago',
          onPressed: () => _cerrar(null),
        ),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_cargando) const LinearProgressIndicator(minHeight: 2, color: Color(0xFFE8806B)),
        ],
      ),
    );
  }
}
