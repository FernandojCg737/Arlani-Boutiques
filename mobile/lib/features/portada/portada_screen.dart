import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../widgets/whatsapp_float_button.dart';
import '../auth/auth_provider.dart';
import '../chatbot/chatbot_panel.dart';
import '../storefront/cart_provider.dart';
import '../storefront/catalogo_provider.dart';
import 'encabezado_plataforma.dart';
import 'estilo_plataforma.dart';
import 'hero_plataforma.dart';
import 'plataforma_data.dart';
import 'seccion_por_que.dart';
import 'secciones_cierre.dart';
import 'secciones_funciones.dart';
import 'secciones_vitrina.dart';

/// Portada de Arlani Boutiques, la plataforma SaaS: la misma pagina de inicio
/// de la web (`pages/home/home.html`) en su version de celular. Encabezado con
/// menu hamburguesa, hero, vitrina de boutiques, promociones, funciones,
/// por que Arlani, precios, llamado final, cinta de logos y pie, mas los
/// botones flotantes del asistente universal y de WhatsApp.
class PortadaScreen extends ConsumerStatefulWidget {
  const PortadaScreen({super.key});

  @override
  ConsumerState<PortadaScreen> createState() => _PortadaScreenState();
}

class _PortadaScreenState extends ConsumerState<PortadaScreen> {
  final _scroll = ScrollController();
  final _claves = {for (final s in SeccionPortada.values) s: GlobalKey()};
  bool _solido = false;
  bool _pasoElHero = false;
  bool _chatAbierto = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_alDesplazar);
    // El carrito del encabezado: se carga con la sesion del cliente.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (ref.read(authProvider).usuario?.isCliente ?? false) {
        ref.read(cartProvider.notifier).cargar();
      }
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _alDesplazar() {
    final y = _scroll.offset;
    final solido = y > 24;
    // Los botones flotantes aparecen cuando el hero sale de la pantalla.
    final pasoElHero = y >= MediaQuery.sizeOf(context).height * 0.85;
    if (solido != _solido || pasoElHero != _pasoElHero) {
      setState(() {
        _solido = solido;
        _pasoElHero = pasoElHero;
      });
    }
  }

  /// Baja hasta la seccion, dejando lugar para el encabezado (`scroll-margin-top`).
  void _irA(SeccionPortada seccion) {
    if (seccion == SeccionPortada.inicio) {
      _scroll.animateTo(
        0,
        duration: const Duration(milliseconds: 600),
        curve: Curves.easeInOutCubic,
      );
      return;
    }
    final objeto = _claves[seccion]?.currentContext?.findRenderObject();
    if (objeto == null) return;
    final destino = RenderAbstractViewport.of(objeto)
        .getOffsetToReveal(objeto, 0)
        .offset;
    final cabecera =
        MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto;
    _scroll.animateTo(
      (destino - cabecera).clamp(0.0, _scroll.position.maxScrollExtent),
      duration: const Duration(milliseconds: 700),
      curve: Curves.easeInOutCubic,
    );
  }

  void _buscar(String texto) {
    ref.read(tiendaFiltrosProvider.notifier).setBusqueda(texto.trim());
    context.go('/catalogo');
  }

  final _reintentos = <ProviderOrFamily, int>{};

  void _reintentar(
    AsyncValue<Object?> estado,
    FutureProvider<Object?> proveedor,
  ) {
    if (!estado.hasError || estado.isLoading) return;
    final intentos = _reintentos[proveedor] ?? 0;
    if (intentos >= 6) return;
    _reintentos[proveedor] = intentos + 1;
    Future.delayed(const Duration(seconds: 4), () {
      if (mounted) ref.invalidate(proveedor);
    });
  }

  Widget _seccion(SeccionPortada s, Widget hijo) =>
      KeyedSubtree(key: _claves[s], child: hijo);

  @override
  Widget build(BuildContext context) {
    // Al iniciar o cerrar sesion se recarga el carrito del encabezado.
    ref.listen(authProvider.select((a) => a.usuario?.isCliente ?? false), (
      antes,
      esCliente,
    ) {
      if (esCliente) {
        ref.read(cartProvider.notifier).cargar();
      } else {
        ref.read(cartProvider.notifier).limpiarLocal();
      }
    });
    // El servidor gratuito se duerme y tarda en despertar mas que el limite de
    // espera de la app: si la carga falla, se reintenta sola unas veces.
    ref.listen(
      tiendasProvider,
      (_, estado) => _reintentar(estado, tiendasProvider),
    );
    ref.listen(
      productosPublicosProvider,
      (_, estado) => _reintentar(estado, productosPublicosProvider),
    );

    // Hora e iconos del sistema en blanco sobre el video y el azul noche.
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(
        statusBarColor: Colors.transparent,
      ),
      child: Scaffold(
        backgroundColor: Plataforma.fondo,
        body: Stack(
          children: [
            RefreshIndicator(
              onRefresh: () async {
                ref.invalidate(tiendasProvider);
                ref.invalidate(productosPublicosProvider);
              },
              edgeOffset:
                  MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto,
              child: SingleChildScrollView(
                controller: _scroll,
                physics: const AlwaysScrollableScrollPhysics(),
                child: Column(
                  children: [
                    HeroPlataforma(
                      onExplorar: () => context.go('/catalogo'),
                      onVerPlanes: () => _irA(SeccionPortada.precios),
                    ),
                    _seccion(
                      SeccionPortada.boutiques,
                      const VitrinaBoutiques(),
                    ),
                    _seccion(
                      SeccionPortada.promociones,
                      const PromocionesBoutiques(),
                    ),
                    _seccion(
                      SeccionPortada.funciones,
                      const FuncionesPlataforma(),
                    ),
                    _seccion(SeccionPortada.porQue, const PorQueArlani()),
                    _seccion(SeccionPortada.precios, const PreciosPlanes()),
                    CtaFinal(onVerPlanes: () => _irA(SeccionPortada.precios)),
                    const CarruselBoutiques(),
                    PiePlataforma(onIrA: _irA),
                  ],
                ),
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: EncabezadoPlataforma(
                solido: _solido,
                onIrA: _irA,
                onBuscar: _buscar,
              ),
            ),
            // Panel del asistente universal, sobre la burbuja (`.chatbot-panel`).
            if (_chatAbierto)
              Positioned(
                left: 16,
                right: 16,
                bottom: 84 + MediaQuery.paddingOf(context).bottom,
                height: (MediaQuery.sizeOf(context).height * 0.7).clamp(0.0, 520.0),
                child: Align(
                  alignment: Alignment.bottomLeft,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 360),
                    child: const ChatbotPanel(),
                  ),
                ),
              ),
            // Asistente universal (izquierda) y WhatsApp (derecha), como en la web.
            Positioned(
              left: 20,
              bottom: 20 + MediaQuery.paddingOf(context).bottom,
              child: _Flotante(
                visible: _pasoElHero || _chatAbierto,
                child: _BotonAsistente(
                  abierto: _chatAbierto,
                  onTap: () => setState(() => _chatAbierto = !_chatAbierto),
                ),
              ),
            ),
            Positioned(
              right: 16,
              bottom: 16 + MediaQuery.paddingOf(context).bottom,
              child: _Flotante(
                visible: _pasoElHero,
                child: const WhatsappFloatButton(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Flotante extends StatelessWidget {
  const _Flotante({required this.visible, required this.child});

  final bool visible;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedOpacity(
        opacity: visible ? 1 : 0,
        duration: const Duration(milliseconds: 200),
        child: child,
      ),
    );
  }
}

/// Burbuja del asistente universal: coral oscuro (`.chatbot--universal`).
class _BotonAsistente extends StatelessWidget {
  const _BotonAsistente({required this.onTap, required this.abierto});

  final VoidCallback onTap;
  final bool abierto;

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
