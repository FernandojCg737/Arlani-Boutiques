import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import '../../widgets/whatsapp_float_button.dart';
import '../cuenta/cuenta_repository.dart';
import '../cuenta/estilo_cuenta.dart';
import '../cuenta/mis_direcciones.dart';
import '../empezar/panel_paypal.dart';
import '../portada/encabezado_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../portada/secciones_cierre.dart';
import 'cart_provider.dart';
import 'catalogo_provider.dart';
import 'checkout_repository.dart';

// Colores de `checkout.scss`.
const _oscuro = Color(0xFF203C40);
const _borde = Color(0xFFE8E5E3);
const _gris = Color(0xFF999999);
const _texto = Color(0xFF555555);

String _bs(double v) => v.toStringAsFixed(2).replaceAll('.', ',');

class _Pagada {
  const _Pagada(this.tienda, this.color, this.ventas, this.pendiente, this.metodo);

  final String tienda;
  final Color color;
  final List<VentaCreada> ventas;
  final bool pendiente;
  final String metodo;
}

enum _Estado { cargando, listo, vacio, error }

/// CU11 + CU21: "Finalizar compra" igual que `pages/checkout` de la web. Cada
/// tienda se paga por separado con sus propios metodos (PayPal en un panel
/// dentro de la pantalla, o QR/transferencia con comprobante); con varias
/// tiendas tambien se puede pagar todo junto. Lo pagado queda arriba y el
/// carrito se vacia de esa tienda.
class CheckoutScreen extends ConsumerStatefulWidget {
  const CheckoutScreen({super.key});

  @override
  ConsumerState<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends ConsumerState<CheckoutScreen> {
  final _scroll = ScrollController();
  final _panelKey = GlobalKey();

  _Estado _estado = _Estado.cargando;
  List<TiendaCheckout> _tiendas = [];
  List<StockItem>? _stock;
  final List<_Pagada> _pagadas = [];
  Map<int, EstadoSucursal> _sucursales = {};

  // Entrega: recojo en la sucursal o envio a una direccion (vale para todo).
  List<DireccionCliente> _direcciones = [];
  String _entrega = 'retiro';
  int? _direccionId;
  bool get _entregaLista => _entrega == 'retiro' || _direccionId != null;
  int? get _direccionEnvio => _entrega == 'envio' ? _direccionId : null;

  // Lo que se esta pagando ahora: una tienda con un metodo, o todo junto.
  int? _empresaActiva;
  MetodoCobro? _metodo;
  bool _modoTodo = false;
  (String, String)? _panel;
  XFile? _archivo;
  bool _procesando = false;
  String? _error;

  CheckoutRepository get _repo => ref.read(checkoutRepositoryProvider);

  @override
  void initState() {
    super.initState();
    _cargar();
    _cargarDirecciones();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    try {
      final tiendas = await _repo.tiendas();
      if (!mounted) return;
      setState(() {
        _tiendas = tiendas;
        _estado = tiendas.isEmpty ? _Estado.vacio : _Estado.listo;
      });
      if (tiendas.isEmpty) return;
      _verificarStock();
      _cargarEstadoSucursales();
    } catch (_) {
      if (mounted) setState(() => _estado = _Estado.error);
    }
  }

  Future<void> _verificarStock() async {
    try {
      final s = await _repo.verificarStock();
      if (mounted) setState(() => _stock = s);
    } catch (_) {
      // La validacion definitiva la hace el backend al registrar la venta.
      if (mounted) setState(() => _stock = []);
    }
  }

  // CU16: sucursales sin caja abierta ahora (se avisa que se prepara al abrir).
  Future<void> _cargarEstadoSucursales() async {
    final ids = {for (final t in _tiendas) for (final i in t.items) i.sucursalId};
    final estados = <int, EstadoSucursal>{};
    await Future.wait(ids.map((id) async {
      try {
        estados[id] = await _repo.estadoSucursal(id);
      } catch (_) {}
    }));
    if (mounted) setState(() => _sucursales = estados);
  }

  Future<void> _cargarDirecciones() async {
    try {
      final ds = await ref.read(cuentaRepositoryProvider).direcciones();
      if (!mounted) return;
      setState(() {
        _direcciones = ds;
        _direccionId = (ds.where((d) => d.predeterminada).firstOrNull ?? ds.firstOrNull)?.id;
      });
    } catch (_) {}
  }

  Future<void> _agregarDireccion() async {
    final d = await abrirHojaCuenta<DireccionCliente>(
      context,
      titulo: 'Nueva dirección de envío',
      subtitulo: 'Marca en el mapa dónde quieres recibir tu pedido.',
      cuerpo: (_) => const FormularioDireccion(),
    );
    if (d == null || !mounted) return;
    setState(() {
      _direcciones = [..._direcciones, d];
      _direccionId = d.id;
      _entrega = 'envio';
    });
  }

  List<StockItem> _faltantes(TiendaCheckout t) {
    final ids = {for (final i in t.items) i.detalleId};
    return [for (final s in _stock ?? <StockItem>[]) if (!s.disponible && ids.contains(s.detalleId)) s];
  }

  bool _puedePagar(TiendaCheckout t) =>
      t.operativa && t.metodos.isNotEmpty && _stock != null && _faltantes(t).isEmpty && _entregaLista;

  List<String> _cerradas(TiendaCheckout t) =>
      {for (final i in t.items) if (_sucursales[i.sucursalId]?.abierta == false) i.sucursalNombre}.toList();

  String? _horario(TiendaCheckout t) {
    for (final i in t.items) {
      final e = _sucursales[i.sucursalId];
      if (e != null && !e.abierta) return e.horario;
    }
    return null;
  }

  void _cerrarPago() {
    _empresaActiva = null;
    _metodo = null;
    _modoTodo = false;
    _panel = null;
    _archivo = null;
  }

  void _elegirEntrega(String e) => setState(() {
        _entrega = e;
        // Cambiar la entrega cierra el pago abierto (se vuelve a abrir).
        _cerrarPago();
      });

  /// Elegir como pagar a una tienda. Con PayPal se abre el panel ahi mismo.
  Future<void> _elegir(TiendaCheckout t, MetodoCobro m) async {
    if (_procesando) return;
    setState(() {
      _error = null;
      _cerrarPago();
      _empresaActiva = t.empresaId;
      _metodo = m;
    });
    if (m.tipo == 'paypal') await _abrirPanel(t.empresaId);
  }

  Future<void> _pagarTodo() async {
    if (_procesando) return;
    setState(() {
      _error = null;
      _cerrarPago();
      _modoTodo = true;
    });
    await _abrirPanel(null);
  }

  Future<void> _abrirPanel(int? empresaId) async {
    setState(() => _procesando = true);
    try {
      final (orderId, url) = await _repo.orden(empresaId);
      if (url == null) throw StateError('sin enlace');
      if (!mounted) return;
      setState(() => _panel = (orderId, url));
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final ctx = _panelKey.currentContext;
        if (ctx != null) Scrollable.ensureVisible(ctx, duration: const Duration(milliseconds: 400), alignment: 0.05);
      });
    } catch (e) {
      if (mounted) setState(() => _error = 'No se pudo iniciar el pago con PayPal. ${extractErrorMessage(e)}');
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _alTerminarPaypal(int? empresaId, String? orderId) async {
    setState(() => _panel = null);
    if (orderId == null) {
      setState(() => _error = 'Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.');
      return;
    }
    setState(() => _procesando = true);
    try {
      final ventas = await _repo.capturar(empresaId, orderId, _direccionEnvio);
      await _registrarPago(empresaId, ventas, false, empresaId == null ? 'Pagar todo (PayPal)' : 'PayPal');
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _elegirFoto() async {
    final f = await ImagePicker().pickImage(source: ImageSource.gallery, imageQuality: 85);
    if (f == null) return;
    if (await f.length() > 5 * 1024 * 1024) {
      setState(() => _error = 'La foto pesa más de 5 MB. Elige una más liviana.');
      return;
    }
    setState(() {
      _archivo = f;
      _error = null;
    });
  }

  Future<void> _enviarComprobante(TiendaCheckout t) async {
    final m = _metodo;
    final f = _archivo;
    if (m == null || f == null || _procesando) return;
    setState(() {
      _procesando = true;
      _error = null;
    });
    try {
      final ventas = await _repo.comprobante(t.empresaId, m.id, f.path, f.name, _direccionEnvio);
      await _registrarPago(t.empresaId, ventas, true, m.nombre);
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  /// Guarda el resultado arriba, saca lo pagado y refresca el carrito (lo de
  /// las demas tiendas sigue para pagarlo despues).
  Future<void> _registrarPago(int? empresaId, List<VentaCreada> ventas, bool pendiente, String metodo) async {
    final porTienda = <String, List<VentaCreada>>{};
    for (final v in ventas) {
      final nombre = v.tiendaNombre ?? _tiendas.where((t) => t.empresaId == empresaId).firstOrNull?.nombre ?? 'Tienda';
      (porTienda[nombre] ??= []).add(v);
    }
    setState(() {
      for (final e in porTienda.entries) {
        final hex = e.value.first.tiendaColor ?? _tiendas.where((t) => t.nombre == e.key).firstOrNull?.colorMarca ?? '#1f2a44';
        _pagadas.add(_Pagada(e.key, colorDesdeHex(hex), e.value, pendiente, metodo));
      }
      _cerrarPago();
    });
    await ref.read(cartProvider.notifier).cargar();
    try {
      final tiendas = await _repo.tiendas();
      if (!mounted) return;
      setState(() {
        _tiendas = tiendas;
        if (tiendas.isEmpty) _estado = _Estado.vacio;
      });
      if (tiendas.isNotEmpty) _verificarStock();
    } catch (_) {
      if (mounted) setState(() => _tiendas = _tiendas.where((t) => t.empresaId != empresaId).toList());
    }
    if (_scroll.hasClients) _scroll.animateTo(0, duration: const Duration(milliseconds: 400), curve: Curves.easeOut);
  }

  void _volver() => context.canPop() ? context.pop() : context.go('/carrito');

  // ---------------------------------------------------------------- pagina

  @override
  Widget build(BuildContext context) {
    final arriba = MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto;
    void irA(SeccionPortada s) => context.go(s == SeccionPortada.inicio ? '/' : '/?seccion=${s.name}');

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: Colors.white,
        body: Stack(
          children: [
            SingleChildScrollView(
              controller: _scroll,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(padding: EdgeInsets.fromLTRB(20, arriba + 40, 20, 72), child: _contenido()),
                  PiePlataforma(onIrA: irA),
                ],
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: EncabezadoPlataforma(
                solido: true,
                pleno: true,
                onIrA: irA,
                onBuscar: (texto) {
                  ref.read(tiendaFiltrosProvider.notifier).setBusqueda(texto.trim());
                  context.go('/catalogo');
                },
              ),
            ),
            Positioned(right: 16, bottom: 16 + MediaQuery.paddingOf(context).bottom, child: const WhatsappFloatButton()),
          ],
        ),
      ),
    );
  }

  Widget _contenido() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerLeft,
          child: InkWell(
            onTap: _volver,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.arrow_back, size: 16, color: _oscuro),
                  const SizedBox(width: 6),
                  Text('VOLVER AL CARRITO',
                      style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5, color: _oscuro)),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 20),
        Text('FINALIZAR COMPRA', style: GoogleFonts.inter(fontSize: 24, fontWeight: FontWeight.w800, color: _oscuro)),
        if (_estado == _Estado.listo && _tiendas.length > 1) ...[
          const SizedBox(height: 8),
          Text(
            'Tu carrito tiene prendas de ${_tiendas.length} tiendas. Cada tienda cobra por separado con sus propios métodos: paga una y luego la siguiente.',
            style: GoogleFonts.inter(fontSize: 14, height: 1.5, color: const Color(0xFF666666)),
          ),
        ],
        const SizedBox(height: 24),
        for (final p in _pagadas) _pagada(p),
        switch (_estado) {
          _Estado.cargando => cargandoCuenta(),
          _Estado.error => Text('No pudimos cargar el checkout. Intenta de nuevo en unos segundos.',
              style: GoogleFonts.inter(fontSize: 14, color: _texto)),
          _Estado.vacio => _vacio(),
          _Estado.listo => _listo(),
        },
      ],
    );
  }

  /// `.checkout-pagada`: lo que ya se pago en esta visita.
  Widget _pagada(_Pagada p) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFEEF7F1),
        border: Border(left: BorderSide(color: p.color, width: 4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(p.tienda, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w800, color: const Color(0xFF1F5135))),
          const SizedBox(height: 4),
          Text(
            p.pendiente
                ? 'Recibimos tu comprobante (${p.metodo}). La tienda lo revisa y te avisamos cuando confirme tu pago.'
                : 'Pagado con ${p.metodo}. Ya puedes recoger tu pedido.',
            style: GoogleFonts.inter(fontSize: 13, height: 1.45, color: const Color(0xFF1F5135)),
          ),
          const SizedBox(height: 6),
          for (final v in p.ventas)
            Text('Compra #${v.id} · ${v.sucursalNombre}',
                style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w600, color: const Color(0xFF1F5135))),
        ],
      ),
    );
  }

  Widget _vacio() {
    final pago = _pagadas.isNotEmpty;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 20),
      decoration: BoxDecoration(border: Border.all(color: _borde)),
      child: Column(
        children: [
          Text(pago ? '¡Listo! No te queda nada por pagar' : 'Tu carrito está vacío',
              textAlign: TextAlign.center, style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w800, color: _oscuro)),
          if (pago) ...[
            const SizedBox(height: 8),
            Text('Puedes ver tus compras y sus facturas en Mi cuenta.',
                textAlign: TextAlign.center, style: GoogleFonts.inter(fontSize: 14, color: const Color(0xFF666666))),
          ],
          const SizedBox(height: 18),
          BotonCuenta(pago ? 'Ver mis compras' : 'Ir al catálogo', onTap: () => context.go(pago ? '/perfil' : '/catalogo')),
        ],
      ),
    );
  }

  Widget _listo() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_error != null) AvisoCuenta(_error!, error: true),
        _entregaSeccion(),
        const SizedBox(height: 24),
        for (final t in _tiendas) ...[_tienda(t), const SizedBox(height: 20)],
        if (_tiendas.length > 1) _todoJunto(),
      ],
    );
  }

  Widget _etiqueta(String texto) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(texto.toUpperCase(), style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: _gris)),
      );

  /// `.checkout-metodo`: opcion con titulo y detalle (activa con el color de la tienda).
  Widget _opcion(String titulo, String detalle, bool activa, VoidCallback? onTap, {Color marca = _oscuro}) {
    return Opacity(
      opacity: onTap == null && !activa ? 0.5 : 1,
      child: InkWell(
        onTap: onTap,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(border: Border.all(color: activa ? marca : const Color(0xFFDDDDDD), width: activa ? 2 : 1)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(titulo, style: GoogleFonts.inter(fontSize: 13.5, fontWeight: FontWeight.w700, color: activa ? _oscuro : _texto)),
              const SizedBox(height: 2),
              Text(detalle, style: GoogleFonts.inter(fontSize: 11.5, color: _gris)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _entregaSeccion() {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: _borde)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _etiqueta('¿Cómo recibes tu pedido?'),
          _opcion('Recojo en sucursal', 'Lo recoges en la sucursal de cada prenda', _entrega == 'retiro', () => _elegirEntrega('retiro')),
          const SizedBox(height: 8),
          _opcion('Envío a domicilio', 'La tienda te lo envía a tu dirección', _entrega == 'envio', () => _elegirEntrega('envio')),
          if (_entrega == 'envio') ...[
            const SizedBox(height: 14),
            for (final d in _direcciones)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: InkWell(
                  onTap: () => setState(() => _direccionId = d.id),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(border: Border.all(color: _direccionId == d.id ? _oscuro : const Color(0xFFE5E2DF))),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(_direccionId == d.id ? Icons.radio_button_checked : Icons.radio_button_unchecked, size: 18, color: _oscuro),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text.rich(
                            TextSpan(
                              children: [
                                TextSpan(text: '${d.alias}  ', style: const TextStyle(fontWeight: FontWeight.w700, color: _oscuro)),
                                TextSpan(text: '${d.direccion}${d.ciudad != null ? ', ${d.ciudad}' : ''}'),
                                if (d.referencia != null && d.referencia!.isNotEmpty)
                                  TextSpan(text: '\n${d.referencia}', style: const TextStyle(fontSize: 12, color: Color(0xFF888888))),
                              ],
                            ),
                            style: GoogleFonts.inter(fontSize: 13, height: 1.4, color: _texto),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: _agregarDireccion,
                style: TextButton.styleFrom(foregroundColor: _oscuro, padding: EdgeInsets.zero),
                child: Text(
                  '+ ${_direcciones.isNotEmpty ? 'Agregar otra dirección' : 'Agregar mi dirección con el mapa'}',
                  style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, decoration: TextDecoration.underline),
                ),
              ),
            ),
            Text('Cada tienda coordina contigo el costo y la hora de entrega.',
                style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF888888))),
          ],
        ],
      ),
    );
  }

  /// `.checkout-tienda`: lo de una tienda, con su color arriba.
  Widget _tienda(TiendaCheckout t) {
    final marca = colorDesdeHex(t.colorMarca);
    final cerradas = _cerradas(t);
    final horario = _horario(t);
    final faltan = _faltantes(t);
    final activa = _empresaActiva == t.empresaId;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(
          top: BorderSide(color: marca, width: 4),
          left: const BorderSide(color: _borde),
          right: const BorderSide(color: _borde),
          bottom: const BorderSide(color: _borde),
        ),
        boxShadow: activa ? const [BoxShadow(color: Color(0x14000000), blurRadius: 16, offset: Offset(0, 6))] : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Cabecera: logo y nombre de la tienda.
          Container(
            padding: const EdgeInsets.all(18),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFF0EEEC)))),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  clipBehavior: Clip.antiAlias,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: t.logoUrl == null ? marca : const Color(0xFFF7F5F3)),
                  alignment: Alignment.center,
                  child: t.logoUrl == null
                      ? Text(t.nombre.characters.first.toUpperCase(),
                          style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w800, color: Colors.white))
                      : ImagenTienda(t.logoUrl!, width: 44, height: 44),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(t.nombre, style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: _oscuro)),
                      Text('Retiras en ${t.sucursales.join(', ')}', style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF888888))),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (cerradas.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(bottom: 14),
                    padding: const EdgeInsets.all(12),
                    decoration: const BoxDecoration(
                      color: Color(0xFFFFF8EC),
                      border: Border(left: BorderSide(color: Color(0xFFE0A040), width: 3)),
                    ),
                    child: Text(
                      '${cerradas.join(', ')} ${cerradas.length == 1 ? 'está cerrada' : 'están cerradas'} en este momento. Tu compra queda registrada: '
                      '${_entrega == 'envio' ? 'la enviamos' : 'la puedes recoger'} cuando la sucursal abra su caja${horario != null ? ' ($horario)' : ''}.',
                      style: GoogleFonts.inter(fontSize: 13, height: 1.45, color: const Color(0xFF6B4A12)),
                    ),
                  ),
                for (final i in t.items)
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE)))),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text('${i.cantidad}× ${i.productoNombre} (${i.tallaCodigo}, ${i.colorNombre})',
                              style: GoogleFonts.inter(fontSize: 13, height: 1.4, color: const Color(0xFF444444))),
                        ),
                        const SizedBox(width: 12),
                        Text('${_bs(i.subtotal)} Bs', style: GoogleFonts.inter(fontSize: 13, color: const Color(0xFF444444))),
                      ],
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text('Total ${t.nombre}', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: _oscuro)),
                      ),
                      Text('${_bs(t.total)} Bs', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: _oscuro)),
                    ],
                  ),
                ),
                if (!t.operativa)
                  _aviso('Esta tienda no está recibiendo pedidos por ahora. Quita sus prendas del carrito para pagar lo demás.')
                else if (t.metodos.isEmpty)
                  _aviso('Esta tienda todavía no configuró cómo cobrar en línea. Puedes pagar en la sucursal o volver más tarde.')
                else if (faltan.isNotEmpty)
                  AvisoCuenta(
                    'Ya no hay stock suficiente de: ${faltan.map((s) => '${s.productoNombre} (${s.tallaCodigo}, ${s.colorNombre}) en ${s.sucursalNombre}: '
                        'pediste ${s.pedida}, hay ${s.disponibleCantidad}').join('; ')}. Vuelve al carrito y ajusta las cantidades o quita esas prendas.',
                    error: true,
                  )
                else ...[
                  _etiqueta('¿Cómo pagas a ${t.nombre}?'),
                  for (final m in t.metodos) ...[
                    _opcion(
                      m.nombre,
                      m.requiereComprobante ? 'Con comprobante' : 'Se confirma al instante',
                      activa && _metodo?.id == m.id,
                      _puedePagar(t) && !_procesando ? () => _elegir(t, m) : null,
                      marca: marca,
                    ),
                    const SizedBox(height: 8),
                  ],
                  if (!_entregaLista)
                    Text('Elige o agrega tu dirección de envío para poder pagar.',
                        style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFF888888))),
                  if (activa && _metodo != null) _pago(t, _metodo!),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _aviso(String texto) => Container(
        padding: const EdgeInsets.all(12),
        color: const Color(0xFFFFF6E5),
        child: Text(texto, style: GoogleFonts.inter(fontSize: 13, height: 1.45, color: const Color(0xFF7A5200))),
      );

  Widget _procesandoTexto(String texto) => Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Row(
          children: [
            const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
            const SizedBox(width: 10),
            Expanded(child: Text(texto, style: GoogleFonts.inter(fontSize: 12.5, color: const Color(0xFF888888)))),
          ],
        ),
      );

  Widget _panelPaypal(int? empresaId) {
    final (orderId, url) = _panel!;
    return Padding(
      key: _panelKey,
      padding: const EdgeInsets.only(top: 12),
      child: PanelPaypal(
        url: url,
        orderId: orderId,
        alto: (MediaQuery.sizeOf(context).height * 0.78).clamp(480.0, 720.0),
        alTerminar: (id) => _alTerminarPaypal(empresaId, id),
      ),
    );
  }

  /// `.checkout-pago`: el panel de PayPal o los datos para pagar con comprobante.
  Widget _pago(TiendaCheckout t, MetodoCobro m) {
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.only(top: 14),
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFFE3DFDC)))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (m.tipo == 'paypal') ...[
            Text('Pagas US\$ ${t.totalUsd.toStringAsFixed(2)} (al cambio oficial) con PayPal; inicia sesión en PayPal y aprueba el pago.',
                style: GoogleFonts.inter(fontSize: 12, height: 1.45, color: const Color(0xFF888888))),
            if (_procesando) _procesandoTexto(_panel == null ? 'Un momento…' : 'Confirmando tu pago…'),
            if (_panel != null) _panelPaypal(t.empresaId),
          ] else ...[
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: const Color(0xFFF7F7F5), border: Border.all(color: const Color(0xFFEEEEEE))),
              child: Column(
                children: [
                  Text('MONTO EXACTO A PAGAR',
                      style: GoogleFonts.inter(fontSize: 10.5, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: _gris)),
                  const SizedBox(height: 4),
                  Text('${_bs(t.total)} Bs', style: GoogleFonts.inter(fontSize: 26, fontWeight: FontWeight.w800, color: _oscuro)),
                ],
              ),
            ),
            if (m.qrUrl != null) ...[
              const SizedBox(height: 12),
              Center(
                child: Container(
                  decoration: BoxDecoration(border: Border.all(color: const Color(0xFFEEEEEE))),
                  child: CachedNetworkImage(imageUrl: resolveImageUrl(m.qrUrl!), width: 220, height: 220, fit: BoxFit.contain),
                ),
              ),
            ],
            if (m.banco != null || m.numeroCuenta != null || m.titular != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                color: const Color(0xFFF7F7F5),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (m.banco != null) _dato('Banco', m.banco!),
                    if (m.numeroCuenta != null) _dato('Cuenta', '${m.numeroCuenta}${m.tipoCuenta != null ? ' · ${m.tipoCuenta}' : ''}'),
                    if (m.titular != null) _dato('Titular', '${m.titular}${m.documentoTitular != null ? ' · ${m.documentoTitular}' : ''}'),
                  ],
                ),
              ),
            ],
            if (m.instrucciones != null) ...[
              const SizedBox(height: 10),
              Text(m.instrucciones!, style: GoogleFonts.inter(fontSize: 13, color: _texto)),
            ],
            const SizedBox(height: 10),
            Text('Paga el monto exacto y sube la foto del comprobante. El personal de ${t.nombre} lo revisa antes de confirmar tu compra.',
                style: GoogleFonts.inter(fontSize: 12, height: 1.45, color: const Color(0xFF888888))),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _procesando ? null : _elegirFoto,
              icon: const Icon(Icons.photo_outlined, size: 18),
              label: Text(_archivo == null ? 'Elegir foto del comprobante' : _archivo!.name,
                  overflow: TextOverflow.ellipsis, style: GoogleFonts.inter(fontSize: 13)),
              style: OutlinedButton.styleFrom(
                foregroundColor: _oscuro,
                side: const BorderSide(color: Color(0xFFDDDDDD)),
                shape: const RoundedRectangleBorder(),
                minimumSize: const Size.fromHeight(46),
              ),
            ),
            const SizedBox(height: 10),
            BotonCuenta(
              _procesando ? 'Enviando…' : 'Enviar comprobante a ${t.nombre}',
              ancho: true,
              onTap: _archivo == null || _procesando ? null : () => _enviarComprobante(t),
            ),
          ],
        ],
      ),
    );
  }

  Widget _dato(String dt, String dd) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Text.rich(
          TextSpan(
            text: '$dt  ',
            style: const TextStyle(color: Color(0xFF888888)),
            children: [TextSpan(text: dd, style: const TextStyle(fontWeight: FontWeight.w600, color: _oscuro))],
          ),
          style: GoogleFonts.inter(fontSize: 13),
        ),
      );

  // ---------------------------------------------------------- pagar todo

  List<TiendaCheckout> get _sinPagarTodo =>
      [for (final t in _tiendas) if (!t.operativa || !t.aceptaPagarTodo || _faltantes(t).isNotEmpty) t];

  String _razon(TiendaCheckout t) {
    if (!t.operativa) return '${t.nombre} no está atendiendo por ahora';
    if (_faltantes(t).isNotEmpty) return '${t.nombre} tiene prendas sin stock';
    if (!t.metodos.any((m) => m.tipo == 'paypal')) return '${t.nombre} no recibe pagos con PayPal';
    return '${t.nombre} todavía no registró el correo de su cuenta PayPal';
  }

  /// `.checkout-todo`: un solo pago con PayPal para todas las tiendas.
  Widget _todoJunto() {
    final total = _tiendas.fold(0.0, (s, t) => s + t.total);
    final usd = _tiendas.fold(0.0, (s, t) => s + t.totalUsd);
    final puede = _stock != null && _sinPagarTodo.isEmpty;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: _modoTodo ? _oscuro : _borde, width: _modoTodo ? 2 : 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            color: const Color(0xFFF7F7F5),
            child: Row(
              children: [
                Expanded(child: Text('Total de tu carrito', style: GoogleFonts.inter(fontSize: 15, color: _oscuro))),
                Text('${_bs(total)} Bs', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: _oscuro)),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: puede
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text('¿Prefieres pagar todo junto?', style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: _oscuro)),
                      const SizedBox(height: 6),
                      Text(
                        'Un solo pago con PayPal (US\$ ${usd.toStringAsFixed(2)}) para las ${_tiendas.length} tiendas. Arlani Boutiques cobra y le envía a cada tienda lo suyo al instante. Recibes una factura de cada tienda.',
                        style: GoogleFonts.inter(fontSize: 13, height: 1.5, color: const Color(0xFF666666)),
                      ),
                      const SizedBox(height: 12),
                      if (!_modoTodo)
                        BotonCuenta('Pagar todo junto', ancho: true, onTap: _procesando || !_entregaLista ? null : _pagarTodo),
                      if (_modoTodo && _procesando) _procesandoTexto(_panel == null ? 'Un momento…' : 'Confirmando tu pago…'),
                      if (_modoTodo && _panel != null) _panelPaypal(null),
                    ],
                  )
                : Text(
                    _stock == null
                        ? 'Revisando el stock…'
                        : 'Pagar todo junto no está disponible: ${_sinPagarTodo.map(_razon).join('; ')}. Paga cada tienda por separado.',
                    style: GoogleFonts.inter(fontSize: 12, height: 1.45, color: const Color(0xFF888888)),
                  ),
          ),
        ],
      ),
    );
  }
}
