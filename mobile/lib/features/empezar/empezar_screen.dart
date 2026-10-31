import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import '../auth/auth_provider.dart';
import '../portada/estilo_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../storefront/catalogo_provider.dart' show publicos;
import 'empezar_repository.dart';
import 'paypal_aprobar_screen.dart';

// Colores de `registro-empresa.scss`.
const _noche = Color(0xFF0B111D);
const _tinta = Color(0xFF121A2C);
const _marfil = Color(0xFFF7F4F2);
const _coral = Color(0xFFE8806B);
const _coralOscuro = Color(0xFFC4503D);
const _oro = Color(0xFFF2B8A6);
const _gris = Color(0xFF5F6779);
const _borde = Color(0xFFDCD7D2);
const _rojo = Color(0xFFC0392B);

const _ciudades = ['Santa Cruz', 'La Paz', 'Cochabamba', 'Sucre', 'Tarija', 'Oruro', 'Potosí', 'Trinidad', 'Cobija'];

/// Colores de marca sugeridos; con el selector se elige cualquier otro.
const _colores = [
  ('Azul noche', '#1f2a44'),
  ('Coral', '#c4503d'),
  ('Verde botella', '#203c40'),
  ('Vino', '#6d2338'),
  ('Negro', '#141414'),
  ('Arena', '#a07d5a'),
];

const _logoMaxBytes = 5 * 1024 * 1024;
final _correo = RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$');
final _subdominioValido = RegExp(r'^[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])$');
const _titulosPasos = ['Plan', 'Tu boutique', 'Confirmar y pagar'];

/// "Mi Boutique Ñandú" -> "mi-boutique-nandu" (igual que `aSubdominio` en la web).
String aSubdominio(String texto) {
  const conTilde = 'áàäâãéèëêíìïîóòöôõúùüûñç';
  const sinTilde = 'aaaaaeeeeiiiiooooouuuunc';
  final buffer = StringBuffer();
  for (final c in texto.toLowerCase().split('')) {
    final i = conTilde.indexOf(c);
    buffer.write(i >= 0 ? sinTilde[i] : c);
  }
  var s = buffer.toString().replaceAll(RegExp(r'[^a-z0-9]+'), '-').replaceAll(RegExp(r'^-+|-+$'), '');
  if (s.length > 30) s = s.substring(0, 30);
  return s;
}

Color _hexAColor(String hex) => Color(int.parse('FF${hex.substring(1)}', radix: 16));

String _colorAHex(Color c) {
  String dos(double v) => (v * 255).round().clamp(0, 255).toRadixString(16).padLeft(2, '0');
  return '#${dos(c.r)}${dos(c.g)}${dos(c.b)}';
}

/// "Crear mi boutique": la misma alta de `/empezar` en la web (version
/// celular), en tres pasos y solo con sesion. El ultimo paso cobra la
/// suscripcion con PayPal dentro de la app; al confirmarse el pago el backend
/// crea la empresa, su suscripcion y su Administrador, y envia las
/// credenciales por correo.
class EmpezarScreen extends ConsumerStatefulWidget {
  const EmpezarScreen({super.key, this.planInicial, this.periodoInicial});

  final String? planInicial;
  final String? periodoInicial;

  @override
  ConsumerState<EmpezarScreen> createState() => _EmpezarScreenState();
}

class _EmpezarScreenState extends ConsumerState<EmpezarScreen> {
  final _scroll = ScrollController();
  int _paso = 0;
  // Los errores se muestran recien al intentar avanzar.
  bool _intento = false;

  // Paso 1: plan
  late String _planId;
  late bool _anual;
  PlanPlataforma get _plan => planesPlataforma.firstWhere((p) => p.id == _planId);

  // Paso 2: boutique
  final _nombreCtrl = TextEditingController();
  final _subdominioCtrl = TextEditingController();
  bool _subdominioEditado = false;
  String _ciudad = 'Santa Cruz';
  final List<String> _publicos = [];
  final _sucursalesCtrl = TextEditingController(text: '1');
  String _color = _colores.first.$2;
  final _hexCtrl = TextEditingController(text: _colores.first.$2);
  Uint8List? _logoBytes;
  String? _logoDataUrl;
  String _logoNombre = '';
  String? _errorLogo;
  late final TextEditingController _adminNombreCtrl;
  final _adminEmailCtrl = TextEditingController();

  // Enlace final: si el escrito ya lo usa otra tienda, con un numero al final.
  Timer? _debounce;
  String? _enlacePedido;
  String? _enlaceLibre;

  // Paso 3
  Cotizacion? _cotizacion;
  bool _cotizando = false;
  bool _procesando = false;
  String? _errorEnvio;
  SuscripcionCreada? _creada;

  @override
  void initState() {
    super.initState();
    _planId = planesPlataforma.any((p) => p.id == widget.planInicial) ? widget.planInicial! : 'basico';
    _anual = widget.periodoInicial == 'anual';
    _adminNombreCtrl = TextEditingController(text: ref.read(authProvider).usuario?.nombre ?? '');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _scroll.dispose();
    _nombreCtrl.dispose();
    _subdominioCtrl.dispose();
    _sucursalesCtrl.dispose();
    _hexCtrl.dispose();
    _adminNombreCtrl.dispose();
    _adminEmailCtrl.dispose();
    super.dispose();
  }

  int get _sucursales => int.tryParse(_sucursalesCtrl.text.trim()) ?? 0;
  String get _subdominio => _subdominioCtrl.text;
  String get _enlaceFinal => _enlacePedido == _subdominio && _enlaceLibre != null ? _enlaceLibre! : _subdominio;
  bool get _enlaceOcupado => _subdominio.length >= 3 && _enlaceFinal != _subdominio;
  String get _prefijoEnlace => '${Uri.parse(webAssetsBaseUrl).host}/tienda-';

  Map<String, String> get _errores {
    final e = <String, String>{};
    final max = _plan.maxSucursales;
    if (_nombreCtrl.text.trim().length < 2) e['nombre'] = 'Escribe el nombre de tu boutique.';
    if (!_subdominioValido.hasMatch(_subdominio)) {
      e['subdominio'] = 'Entre 3 y 30 letras, números o guiones (sin espacios ni acentos).';
    }
    if (_sucursales < 1 || _sucursales > max) {
      e['sucursales'] = 'Tu plan ${_plan.nombre} permite de 1 a $max ${max == 1 ? 'sucursal' : 'sucursales'}.';
    }
    if (_adminNombreCtrl.text.trim().length < 2) e['adminNombre'] = 'Escribe el nombre del administrador.';
    final email = _adminEmailCtrl.text.trim();
    if (!_correo.hasMatch(email)) {
      e['adminEmail'] = 'Escribe un correo válido.';
    } else if (email.toLowerCase() == ref.read(authProvider).usuario?.email.toLowerCase()) {
      e['adminEmail'] = 'Usa un correo distinto al de tu cuenta de cliente.';
    }
    return e;
  }

  String? _error(String campo) => _intento ? _errores[campo] : null;

  SolicitudSuscripcion get _solicitud => SolicitudSuscripcion(
        plan: _planId,
        periodo: _anual ? 'anual' : 'mensual',
        nombre: _nombreCtrl.text.trim(),
        subdominio: _subdominio,
        ciudad: _ciudad,
        sucursales: _sucursales,
        publicos: List.of(_publicos),
        color: _color,
        adminNombre: _adminNombreCtrl.text.trim(),
        adminEmail: _adminEmailCtrl.text.trim().toLowerCase(),
      );

  void _arriba() {
    if (_scroll.hasClients) _scroll.animateTo(0, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
  }

  void _siguiente() {
    const campos = {
      0: <String>[],
      1: ['nombre', 'subdominio', 'sucursales', 'adminNombre', 'adminEmail'],
    };
    if ((campos[_paso] ?? const []).any(_errores.containsKey)) {
      setState(() => _intento = true);
      return;
    }
    setState(() {
      _intento = false;
      if (_paso < 2) _paso++;
    });
    if (_paso == 2) _cotizar();
    _arriba();
  }

  void _anterior() {
    if (_procesando) return;
    setState(() {
      _intento = false;
      _errorEnvio = null;
      if (_paso > 0) _paso--;
    });
    _arriba();
  }

  // Solo se vuelve a pasos ya visitados.
  void _irAPaso(int destino) {
    if (destino >= _paso || _procesando || _creada != null) return;
    setState(() {
      _intento = false;
      _errorEnvio = null;
      _paso = destino;
    });
    _arriba();
  }

  void _elegirPlan(String id) {
    setState(() {
      _planId = id;
      final n = _sucursales.clamp(1, _plan.maxSucursales);
      _sucursalesCtrl.text = '$n';
    });
  }

  void _alCambiarNombre(String valor) {
    if (!_subdominioEditado) _ponerSubdominio(aSubdominio(valor));
    setState(() {});
  }

  void _alCambiarSubdominio(String valor) {
    _subdominioEditado = true;
    final limpio = aSubdominio(valor);
    if (limpio != valor) {
      _subdominioCtrl.value = TextEditingValue(text: limpio, selection: TextSelection.collapsed(offset: limpio.length));
    }
    _ponerSubdominio(limpio);
    setState(() {});
  }

  void _ponerSubdominio(String s) {
    if (_subdominioCtrl.text != s) _subdominioCtrl.text = s;
    _debounce?.cancel();
    if (s.length < 3) return;
    _debounce = Timer(const Duration(milliseconds: 300), () async {
      try {
        final libre = await ref.read(empezarRepositoryProvider).enlaceDisponible(s);
        if (mounted && _subdominioCtrl.text == s) {
          setState(() {
            _enlacePedido = s;
            _enlaceLibre = libre;
          });
        }
      } catch (_) {
        // Sin respuesta: se muestra lo escrito.
      }
    });
  }

  void _elegirColor(String hex) {
    final h = hex.trim().startsWith('#') ? hex.trim() : '#${hex.trim()}';
    if (!RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(h)) return;
    setState(() {
      _color = h.toLowerCase();
      _hexCtrl.text = _color;
    });
  }

  Future<void> _abrirSelectorColor() async {
    final elegido = await showDialog<String>(context: context, builder: (_) => _SelectorColor(inicial: _color));
    if (elegido != null) _elegirColor(elegido);
  }

  // Logo en cualquier formato de imagen: se manda como data URL y el backend
  // lo convierte (igual que la web).
  Future<void> _elegirLogo() async {
    setState(() => _errorLogo = null);
    final archivo = await ImagePicker().pickImage(source: ImageSource.gallery);
    if (archivo == null) return;
    final bytes = await archivo.readAsBytes();
    if (bytes.length > _logoMaxBytes) {
      setState(() => _errorLogo = 'El logo pesa más de 5 MB. Elige una imagen más liviana.');
      return;
    }
    final nombre = archivo.name.toLowerCase();
    final ext = nombre.contains('.') ? nombre.split('.').last : 'png';
    final mime = archivo.mimeType ??
        switch (ext) {
          'jpg' || 'jpeg' => 'image/jpeg',
          'svg' => 'image/svg+xml',
          'heic' || 'heif' => 'image/heic',
          _ => 'image/$ext',
        };
    setState(() {
      _logoBytes = bytes;
      _logoDataUrl = 'data:$mime;base64,${base64Encode(bytes)}';
      _logoNombre = archivo.name;
    });
  }

  void _quitarLogo() => setState(() {
        _logoBytes = null;
        _logoDataUrl = null;
        _logoNombre = '';
      });

  // Al llegar a "Confirmar": precio en Bs y US$ y validacion antes de cobrar.
  Future<void> _cotizar() async {
    setState(() {
      _cotizacion = null;
      _errorEnvio = null;
      _cotizando = true;
    });
    try {
      final c = await ref.read(empezarRepositoryProvider).cotizar(_solicitud);
      if (mounted) setState(() => _cotizacion = c);
    } catch (e) {
      if (mounted) {
        setState(() => _errorEnvio = _mensaje(e, 'No pudimos calcular el precio. Revisa tu conexión e inténtalo de nuevo.'));
      }
    } finally {
      if (mounted) setState(() => _cotizando = false);
    }
  }

  // "Pagar mi suscripcion": PayPal se abre dentro de la app.
  Future<void> _pagar() async {
    setState(() {
      _errorEnvio = null;
      _procesando = true;
    });
    try {
      final (orderId, approveUrl) = await ref.read(empezarRepositoryProvider).crearOrden(_solicitud);
      if (!mounted) return;
      if (approveUrl == null) throw StateError('sin enlace');
      setState(() => _procesando = false);
      final aprobada = await Navigator.of(context).push<String>(
        MaterialPageRoute(builder: (_) => PaypalAprobarScreen(url: approveUrl, orderId: orderId)),
      );
      if (!mounted) return;
      if (aprobada == null) {
        setState(() => _errorEnvio = 'Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.');
        return;
      }
      await _confirmar(aprobada);
    } catch (e) {
      if (mounted) setState(() => _errorEnvio = _mensaje(e, 'No se pudo iniciar el pago con PayPal. Inténtalo de nuevo.'));
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _confirmar(String? orderId) async {
    setState(() {
      _procesando = true;
      _errorEnvio = null;
    });
    try {
      final creada = await ref.read(empezarRepositoryProvider).confirmar(_solicitud, orderId, _logoDataUrl);
      if (mounted) setState(() => _creada = creada);
      _arriba();
    } catch (e) {
      if (mounted) {
        setState(() => _errorEnvio = _mensaje(e, 'No pudimos registrar tu boutique. Si se te cobró, escríbenos y lo resolvemos.'));
      }
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  // El administrador entra con su cuenta nueva: se cierra la sesion de cliente.
  Future<void> _irAlPanel() async {
    await ref.read(authProvider.notifier).logout();
    if (mounted) context.go('/login');
  }

  void _volverAArlani() => context.canPop() ? context.pop() : context.go('/');

  // El detalle del backend si lo hay; si no, el mensaje de cada caso.
  String _mensaje(Object e, String porDefecto) => e is DioException ? extractErrorMessage(e) : porDefecto;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      // Atras del sistema: vuelve un paso antes de salir.
      canPop: _paso == 0 || _creada != null,
      onPopInvokedWithResult: (salio, _) {
        if (!salio) _anterior();
      },
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
        child: Scaffold(
          backgroundColor: _marfil,
          body: Column(
            children: [
              _cabecera(),
              Expanded(
                child: SingleChildScrollView(
                  controller: _scroll,
                  padding: EdgeInsets.fromLTRB(20, 24, 20, 32 + MediaQuery.paddingOf(context).bottom),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: InkWell(
                          onTap: _volverAArlani,
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(Icons.chevron_left, size: 20, color: _gris),
                                Text('Volver a Arlani', style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600, color: _gris)),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 28),
                      if (_creada != null) _listo(_creada!) else ...[
                        switch (_paso) {
                          0 => _pasoPlan(),
                          1 => _pasoBoutique(),
                          _ => _pasoConfirmar(),
                        },
                        const SizedBox(height: 28),
                        _acciones(),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ------------------------------------------------------------ cabecera

  /// `.lateral` en celular: logo y la barra de pasos.
  Widget _cabecera() {
    // Azul noche con un brillo coral suave abajo al centro (el
    // `radial-gradient(80% 50% at 50% 100%, ...)` de la web).
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: _noche,
        // Opaco de punta a punta: el coral al 22 % ya mezclado con el azul noche.
        gradient: RadialGradient(
          center: Alignment(0, 1.6),
          radius: 1.1,
          colors: [Color(0xFF3C292E), _noche],
          stops: [0, 1],
        ),
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(20, MediaQuery.paddingOf(context).top + 18, 20, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GestureDetector(
              onTap: () => context.go('/'),
              child: Image.asset('assets/portada/arlani-logo-encabezado.png', height: 44, semanticLabel: 'Arlani Boutiques'),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                for (var i = 0; i < _titulosPasos.length; i++) ...[
                  if (i > 0) const SizedBox(width: 8),
                  Expanded(
                    child: Semantics(
                      button: i < _paso,
                      label: 'Paso ${i + 1}: ${_titulosPasos[i]}',
                      child: GestureDetector(
                        onTap: () => _irAPaso(i),
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          color: Colors.transparent,
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 300),
                            height: 4,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(2),
                              color: i < _paso || _creada != null
                                  ? _oro
                                  : i == _paso
                                      ? _coral
                                      : Colors.white.withValues(alpha: 0.15),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ---------------------------------------------------------------- textos

  Widget _titulo(String texto) =>
      Text(texto, style: bricolage(size: 32, weight: FontWeight.w500, color: _tinta, height: 1.15));

  Widget _bajada(String texto) => Padding(
        padding: const EdgeInsets.only(top: 10, bottom: 24),
        child: Text(texto, style: GoogleFonts.inter(fontSize: 15.5, height: 1.45, color: _gris)),
      );

  Widget _etiqueta(String texto, {String? pequeno}) => Padding(
        padding: const EdgeInsets.only(bottom: 7),
        child: Text.rich(
          TextSpan(
            text: texto,
            children: [
              if (pequeno != null)
                TextSpan(text: ' $pequeno', style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w400, color: _gris)),
            ],
          ),
          style: GoogleFonts.inter(fontSize: 13.8, fontWeight: FontWeight.w600, color: _tinta),
        ),
      );

  Widget _textoError(String? msg) => msg == null
      ? const SizedBox.shrink()
      : Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(msg, style: GoogleFonts.inter(fontSize: 12.8, color: _rojo)),
        );

  InputDecoration _decoracion({String? pista, bool error = false}) {
    OutlineInputBorder borde(Color c) =>
        OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: c, width: 1.5));
    return InputDecoration(
      hintText: pista,
      hintStyle: GoogleFonts.inter(color: const Color(0xFFA9A49F), fontSize: 16),
      filled: true,
      fillColor: Colors.white,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: borde(error ? _rojo : _borde),
      enabledBorder: borde(error ? _rojo : _borde),
      focusedBorder: borde(error ? _rojo : _coral),
    );
  }

  Widget _campo({
    required String etiqueta,
    required TextEditingController ctrl,
    String? pista,
    String? error,
    TextInputType? teclado,
    ValueChanged<String>? onChanged,
    int? maxLength,
    String? pequeno,
    Widget? debajo,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _etiqueta(etiqueta, pequeno: pequeno),
          TextField(
            controller: ctrl,
            keyboardType: teclado,
            maxLength: maxLength,
            onChanged: onChanged ?? (_) => setState(() {}),
            style: GoogleFonts.inter(fontSize: 16, color: _tinta),
            decoration: _decoracion(pista: pista, error: error != null).copyWith(counterText: ''),
          ),
          _textoError(error),
          ?debajo,
        ],
      ),
    );
  }

  // --------------------------------------------------------------- paso 1

  Widget _pasoPlan() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _titulo('Elige tu plan'),
        _bajada('Puedes cambiarlo cuando quieras desde tu panel.'),
        // `.periodo`
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(color: const Color(0xFFEBE6E1), borderRadius: BorderRadius.circular(999)),
          child: Row(
            children: [
              _botonPeriodo('Mensual', !_anual, () => setState(() => _anual = false)),
              _botonPeriodo('Anual', _anual, () => setState(() => _anual = true), insignia: '2 meses gratis'),
            ],
          ),
        ),
        const SizedBox(height: 22),
        for (final p in planesPlataforma) ...[_tarjetaPlan(p), const SizedBox(height: 12)],
      ],
    );
  }

  Widget _botonPeriodo(String texto, bool activo, VoidCallback onTap, {String? insignia}) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: activo ? Colors.white : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
            boxShadow: activo ? const [BoxShadow(color: Color(0x14000000), blurRadius: 6, offset: Offset(0, 2))] : null,
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(texto, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600, color: activo ? _tinta : _gris)),
              if (insignia != null) ...[
                const SizedBox(width: 6),
                Flexible(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(color: const Color(0x2EE8806B), borderRadius: BorderRadius.circular(999)),
                    child: Text(insignia,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, color: _coralOscuro)),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _tarjetaPlan(PlanPlataforma p) {
    final elegido = _planId == p.id;
    final suc = p.maxSucursales == 1 ? 'sucursal' : 'sucursales';
    return Semantics(
      selected: elegido,
      button: true,
      child: GestureDetector(
        onTap: () => _elegirPlan(p.id),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: elegido ? _coral : _borde, width: 1.5),
            boxShadow: elegido ? const [BoxShadow(color: Color(0x26E8806B), spreadRadius: 3)] : null,
          ),
          child: Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 20,
                height: 20,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: elegido ? _coral : _borde, width: elegido ? 6 : 2),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(p.nombre, style: GoogleFonts.inter(fontSize: 16.3, fontWeight: FontWeight.w700, color: _tinta)),
                    const SizedBox(height: 2),
                    Text('${p.resumen} Hasta ${p.maxSucursales} $suc.',
                        style: GoogleFonts.inter(fontSize: 13.4, height: 1.35, color: _gris)),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Text.rich(
                TextSpan(
                  text: p.esPrueba ? 'Gratis' : 'Bs ${p.precioPorMes(_anual)}',
                  children: [
                    TextSpan(
                      text: p.esPrueba ? ' ${p.diasPrueba} días' : ' / mes',
                      style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w500, color: _gris),
                    ),
                  ],
                ),
                style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w700, color: _tinta),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // --------------------------------------------------------------- paso 2

  Widget _pasoBoutique() {
    final max = _plan.maxSucursales;
    final inicial = (_nombreCtrl.text.trim().isEmpty ? 'T' : _nombreCtrl.text.trim()[0]).toUpperCase();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _titulo('Cuéntanos de tu boutique'),
        _bajada('Así la verán tus clientes.'),
        _campo(
          etiqueta: 'Nombre de la boutique',
          ctrl: _nombreCtrl,
          pista: 'Ej.: Atelier Aranier',
          maxLength: 60,
          error: _error('nombre'),
          onChanged: _alCambiarNombre,
        ),
        // `.campo__compuesto`: prefijo del enlace + lo que se escribe.
        Padding(
          padding: const EdgeInsets.only(bottom: 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _etiqueta('Enlace de tu tienda'),
              Container(
                clipBehavior: Clip.antiAlias,
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: _error('subdominio') != null ? _rojo : _borde, width: 1.5),
                ),
                child: Row(
                  children: [
                    Flexible(
                      child: Container(
                        color: const Color(0xFFF1EDE9),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 15),
                        child: Text(_prefijoEnlace,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: GoogleFonts.inter(fontSize: 14.7, color: _gris)),
                      ),
                    ),
                    SizedBox(
                      width: 120,
                      child: TextField(
                        controller: _subdominioCtrl,
                        maxLength: 30,
                        autocorrect: false,
                        enableSuggestions: false,
                        onChanged: _alCambiarSubdominio,
                        style: GoogleFonts.inter(fontSize: 16, color: _tinta),
                        decoration: const InputDecoration(
                          counterText: '',
                          isDense: true,
                          filled: false,
                          border: InputBorder.none,
                          enabledBorder: InputBorder.none,
                          focusedBorder: InputBorder.none,
                          contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 14),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (_error('subdominio') != null)
                _textoError(_error('subdominio'))
              else if (_enlaceOcupado)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text.rich(
                    TextSpan(
                      text: 'Ya hay una boutique con ese enlace: la tuya quedará como ',
                      children: [
                        TextSpan(text: '$_prefijoEnlace$_enlaceFinal', style: const TextStyle(fontWeight: FontWeight.w700)),
                        const TextSpan(text: '.'),
                      ],
                    ),
                    style: GoogleFonts.inter(fontSize: 12.8, color: const Color(0xFF9A5B12)),
                  ),
                ),
            ],
          ),
        ),
        // Para quien vende: se puede elegir mas de uno.
        Padding(
          padding: const EdgeInsets.only(bottom: 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _etiqueta('¿Para quién vendes?', pequeno: '(puedes elegir varios)'),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final (id, etiqueta) in publicos)
                    _chip(etiqueta, _publicos.contains(id), () {
                      setState(() => _publicos.contains(id) ? _publicos.remove(id) : _publicos.add(id));
                    }),
                ],
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(bottom: 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _etiqueta('Ciudad'),
              DropdownButtonFormField<String>(
                initialValue: _ciudad,
                isExpanded: true,
                icon: const Icon(Icons.keyboard_arrow_down, color: _tinta),
                style: GoogleFonts.inter(fontSize: 16, color: _tinta),
                decoration: _decoracion(),
                items: [for (final c in _ciudades) DropdownMenuItem(value: c, child: Text(c))],
                onChanged: (c) => setState(() => _ciudad = c ?? _ciudad),
              ),
            ],
          ),
        ),
        _campo(
          etiqueta: 'Sucursales',
          pequeno: '(máx. $max)',
          ctrl: _sucursalesCtrl,
          teclado: TextInputType.number,
          error: _error('sucursales'),
          debajo: _error('sucursales') != null
              ? null
              : Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Wrap(
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text('El plan ${_plan.nombre} admite hasta $max. ', style: GoogleFonts.inter(fontSize: 12.8, color: _gris)),
                      if (max < 10)
                        GestureDetector(
                          onTap: () => _irAPaso(0),
                          child: Text('Ver planes',
                              style: GoogleFonts.inter(
                                fontSize: 12.8,
                                fontWeight: FontWeight.w700,
                                color: _coralOscuro,
                                decoration: TextDecoration.underline,
                                decorationColor: _coralOscuro,
                              )),
                        ),
                    ],
                  ),
                ),
        ),
        // `.colores`
        Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Text('Color de tu marca', style: GoogleFonts.inter(fontSize: 13.8, fontWeight: FontWeight.w600, color: _tinta)),
              ),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  for (final (nombre, valor) in _colores)
                    _muestraColor(
                      descripcion: nombre,
                      elegido: _color == valor,
                      onTap: () => _elegirColor(valor),
                      child: DecoratedBox(decoration: BoxDecoration(color: _hexAColor(valor), shape: BoxShape.circle)),
                    ),
                  _muestraColor(
                    descripcion: 'Elegir cualquier color',
                    elegido: !_colores.any((c) => c.$2 == _color),
                    onTap: _abrirSelectorColor,
                    child: const DecoratedBox(
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: SweepGradient(colors: [
                          Color(0xFFFF0000), Color(0xFFFFFF00), Color(0xFF00FF00), Color(0xFF00FFFF),
                          Color(0xFF0000FF), Color(0xFFFF00FF), Color(0xFFFF0000),
                        ]),
                      ),
                    ),
                  ),
                  // `.colores__hex`
                  Container(
                    width: 124,
                    height: 40,
                    padding: const EdgeInsets.only(left: 12, right: 8),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(color: _borde, width: 1.5),
                    ),
                    child: Row(
                      children: [
                        Container(width: 14, height: 14, decoration: BoxDecoration(color: _hexAColor(_color), shape: BoxShape.circle)),
                        const SizedBox(width: 8),
                        Expanded(
                          child: TextField(
                            controller: _hexCtrl,
                            maxLength: 7,
                            autocorrect: false,
                            onSubmitted: _elegirColor,
                            onChanged: (v) {
                              if (v.length == 7) _elegirColor(v);
                            },
                            style: GoogleFonts.robotoMono(fontSize: 14, color: _tinta),
                            decoration: const InputDecoration(
                              counterText: '',
                              isDense: true,
                              filled: false,
                              border: InputBorder.none,
                              enabledBorder: InputBorder.none,
                              focusedBorder: InputBorder.none,
                              contentPadding: EdgeInsets.zero,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        // `.logo`
        Padding(
          padding: const EdgeInsets.only(bottom: 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _etiqueta('Logo de tu boutique', pequeno: '(opcional)'),
              Row(
                children: [
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 400),
                    width: 72,
                    height: 72,
                    clipBehavior: Clip.antiAlias,
                    decoration: BoxDecoration(color: _hexAColor(_color), borderRadius: BorderRadius.circular(16)),
                    alignment: Alignment.center,
                    child: _logoBytes != null
                        ? Padding(
                            padding: const EdgeInsets.all(8),
                            child: Image.memory(
                              _logoBytes!,
                              fit: BoxFit.contain,
                              errorBuilder: (_, _, _) => const Icon(Icons.image_outlined, color: Colors.white, size: 30),
                            ),
                          )
                        : Text(inicial, style: GoogleFonts.inter(fontSize: 25.6, fontWeight: FontWeight.w700, color: Colors.white)),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: 14,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            _botonPildora(_logoBytes != null ? 'Cambiar logo' : 'Subir logo', _elegirLogo, chico: true),
                            if (_logoBytes != null)
                              GestureDetector(
                                onTap: _quitarLogo,
                                child: Text('Quitar',
                                    style: GoogleFonts.inter(
                                      fontSize: 13.6,
                                      fontWeight: FontWeight.w700,
                                      color: _coralOscuro,
                                      decoration: TextDecoration.underline,
                                      decorationColor: _coralOscuro,
                                    )),
                              ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          _logoBytes != null ? _logoNombre : 'Cualquier formato de imagen (PNG, JPG, SVG, WEBP, HEIC…), hasta 5 MB.',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.inter(fontSize: 12.8, color: _gris),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              _textoError(_errorLogo),
            ],
          ),
        ),
        // `.admin`
        Container(
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 4),
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(14), border: Border.all(color: _borde, width: 1.5)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Cuenta del administrador', style: GoogleFonts.inter(fontSize: 14.4, fontWeight: FontWeight.w700, color: _tinta)),
              const SizedBox(height: 10),
              Text.rich(
                TextSpan(
                  text: 'Con este correo entrarás al panel de tu boutique. La contraseña te la enviaremos a tu correo ',
                  children: [
                    TextSpan(
                      text: ref.watch(authProvider).usuario?.email ?? '',
                      style: const TextStyle(fontWeight: FontWeight.w700, color: _tinta),
                    ),
                    const TextSpan(text: '.'),
                  ],
                ),
                style: GoogleFonts.inter(fontSize: 14, height: 1.5, color: _gris),
              ),
              const SizedBox(height: 16),
              _campo(etiqueta: 'Nombre', ctrl: _adminNombreCtrl, maxLength: 150, error: _error('adminNombre')),
              _campo(
                etiqueta: 'Correo',
                ctrl: _adminEmailCtrl,
                pista: 'admin@tuboutique.com',
                teclado: TextInputType.emailAddress,
                maxLength: 150,
                error: _error('adminEmail'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _chip(String texto, bool activo, VoidCallback onTap) {
    return Semantics(
      button: true,
      selected: activo,
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
          decoration: BoxDecoration(
            color: activo ? _tinta : Colors.white,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: activo ? _tinta : _borde, width: 1.5),
          ),
          child: Text(texto, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w500, color: activo ? Colors.white : _tinta)),
        ),
      ),
    );
  }

  Widget _muestraColor({required String descripcion, required bool elegido, required VoidCallback onTap, required Widget child}) {
    return Semantics(
      button: true,
      selected: elegido,
      label: descripcion,
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: 48,
          height: 48,
          padding: const EdgeInsets.all(5),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: elegido ? _tinta : Colors.transparent, width: 2),
          ),
          child: child,
        ),
      ),
    );
  }

  Widget _botonPildora(String texto, VoidCallback? onTap, {bool lleno = false, bool chico = false}) {
    final estilo = GoogleFonts.inter(fontSize: chico ? 14 : 15.2, fontWeight: FontWeight.w700);
    final relleno = EdgeInsets.symmetric(horizontal: chico ? 18 : 26, vertical: chico ? 10 : 15);
    return lleno
        ? FilledButton(
            onPressed: onTap,
            style: FilledButton.styleFrom(
              backgroundColor: _tinta,
              foregroundColor: Colors.white,
              disabledBackgroundColor: _tinta.withValues(alpha: 0.5),
              disabledForegroundColor: Colors.white,
              shape: const StadiumBorder(),
              padding: relleno,
              textStyle: estilo,
            ),
            child: Text(texto),
          )
        : OutlinedButton(
            onPressed: onTap,
            style: OutlinedButton.styleFrom(
              foregroundColor: _tinta,
              backgroundColor: Colors.transparent,
              side: const BorderSide(color: _borde, width: 1.5),
              shape: const StadiumBorder(),
              padding: relleno,
              textStyle: estilo,
            ),
            child: Text(texto),
          );
  }

  // --------------------------------------------------------------- paso 3

  Widget _pasoConfirmar() {
    final c = _cotizacion;
    final suc = _sucursales == 1 ? 'sucursal' : 'sucursales';
    final plan = _plan;
    final periodoTexto = plan.esPrueba ? '${plan.diasPrueba} días gratis' : (_anual ? 'Anual' : 'Mensual');
    final monto = _anual ? plan.precioAnual : plan.precioPorMes(false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _titulo('Confirma y paga'),
        _bajada('Si algo no está bien, vuelve al paso que quieras con «Atrás» o tocando la barra de arriba.'),
        const Divider(color: _borde, height: 1),
        _filaResumen('Boutique', _nombreCtrl.text.trim(), color: _hexAColor(_color)),
        _filaResumen('Enlace', '$_prefijoEnlace${c?.subdominio ?? _enlaceFinal}'),
        _filaResumen('Ciudad y sucursales', '$_ciudad · $_sucursales $suc'),
        _filaResumen('Administrador', '${_adminNombreCtrl.text.trim()} · ${_adminEmailCtrl.text.trim()}'),
        _filaResumen('Plan', '${plan.nombre} · $periodoTexto'),
        const SizedBox(height: 20),
        // `.total`
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(color: _tinta, borderRadius: BorderRadius.circular(14)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                plan.esPrueba ? '${plan.diasPrueba} días de prueba' : (_anual ? 'Total por año' : 'Total por mes'),
                style: GoogleFonts.inter(fontSize: 14, color: Colors.white.withValues(alpha: 0.7)),
              ),
              const SizedBox(height: 4),
              Text(plan.esPrueba ? 'Gratis' : 'Bs $monto', style: bricolage(size: 28.8, weight: FontWeight.w600, color: Colors.white)),
              if (!plan.esPrueba) ...[
                const SizedBox(height: 4),
                if (c != null)
                  Text.rich(
                    TextSpan(
                      text: 'Pagas ',
                      children: [
                        TextSpan(text: 'US\$ ${c.montoUsd}', style: const TextStyle(fontWeight: FontWeight.w700, color: Colors.white)),
                        TextSpan(text: ' con PayPal · tipo de cambio oficial Bs ${c.tipoCambio}'),
                      ],
                    ),
                    style: GoogleFonts.inter(fontSize: 12.8, color: Colors.white.withValues(alpha: 0.7)),
                  )
                else if (_cotizando)
                  Text('Calculando el monto en dólares…',
                      style: GoogleFonts.inter(fontSize: 12.8, color: Colors.white.withValues(alpha: 0.7))),
              ],
            ],
          ),
        ),
        if (_errorEnvio != null) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: const Color(0xFFFDECEA), borderRadius: BorderRadius.circular(10)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_errorEnvio!, style: GoogleFonts.inter(fontSize: 14.4, color: const Color(0xFFA12A1D))),
                if (c == null && !_cotizando)
                  GestureDetector(
                    onTap: _cotizar,
                    child: Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text('Reintentar',
                          style: GoogleFonts.inter(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: _coralOscuro,
                            decoration: TextDecoration.underline,
                            decorationColor: _coralOscuro,
                          )),
                    ),
                  ),
              ],
            ),
          ),
        ],
        if (_procesando) ...[
          const SizedBox(height: 16),
          Row(
            children: [
              const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: _coral)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  plan.esPrueba ? 'Activando tu prueba…' : 'Un momento: preparando o confirmando tu pago…',
                  style: GoogleFonts.inter(fontSize: 14, color: _gris),
                ),
              ),
            ],
          ),
        ],
        if (!plan.esPrueba) ...[
          const SizedBox(height: 12),
          Text('Pago seguro con PayPal dentro de la app.', style: GoogleFonts.inter(fontSize: 12.8, color: _gris)),
        ],
      ],
    );
  }

  Widget _filaResumen(String dt, String dd, {Color? color}) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _borde))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(dt, style: GoogleFonts.inter(fontSize: 14.4, color: _gris)),
          const SizedBox(width: 16),
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (color != null) ...[
                  Container(width: 12, height: 12, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                  const SizedBox(width: 8),
                ],
                Flexible(
                  child: Text(dd,
                      textAlign: TextAlign.right,
                      style: GoogleFonts.inter(fontSize: 14.7, fontWeight: FontWeight.w600, color: _tinta)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ------------------------------------------------------------- acciones

  Widget _acciones() {
    final plan = _plan;
    return Wrap(
      alignment: WrapAlignment.end,
      spacing: 10,
      runSpacing: 10,
      children: [
        if (_paso > 0) _botonPildora('Atrás', _procesando ? null : _anterior),
        if (_paso < 2)
          _botonPildora('Continuar', _siguiente, lleno: true)
        else if (plan.esPrueba)
          _botonPildora(
            _procesando ? 'Activando tu prueba…' : 'Activar mi prueba gratis',
            _cotizacion == null || _procesando ? null : () => _confirmar(null),
            lleno: true,
          )
        else
          _botonPildora('Pagar mi suscripción', _cotizacion == null || _procesando ? null : _pagar, lleno: true),
      ],
    );
  }

  // ------------------------------------------------------------------ listo

  Widget _listo(SuscripcionCreada c) {
    final pagado = c.metodo == 'paypal';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 64,
          height: 64,
          decoration: const BoxDecoration(color: Color(0xFFE3F6EC), shape: BoxShape.circle),
          child: const Icon(Icons.check, color: Color(0xFF1D6B45), size: 34),
        ),
        const SizedBox(height: 20),
        _titulo(pagado ? '¡Pago confirmado!' : '¡Tu prueba está activa!'),
        const SizedBox(height: 12),
        Text.rich(
          TextSpan(
            children: [
              TextSpan(text: c.empresaNombre, style: const TextStyle(fontWeight: FontWeight.w700, color: _tinta)),
              TextSpan(text: ' ya es parte de Arlani con el plan ${c.planNombre}.'),
              if (pagado) ...[
                const TextSpan(text: ' Pagaste '),
                TextSpan(text: 'US\$ ${c.montoUsd}', style: const TextStyle(fontWeight: FontWeight.w700, color: _tinta)),
                TextSpan(text: ' (Bs ${c.montoBob}).'),
              ],
            ],
          ),
          style: GoogleFonts.inter(fontSize: 16.3, height: 1.5, color: _gris),
        ),
        const SizedBox(height: 20),
        if (c.correoEnviado)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(14), border: Border.all(color: _borde)),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.mail_outline, color: _coralOscuro),
                const SizedBox(width: 12),
                Expanded(
                  child: Text.rich(
                    TextSpan(
                      text: 'Revisa tu correo ',
                      children: [
                        TextSpan(text: c.correoDestino, style: const TextStyle(fontWeight: FontWeight.w700, color: _tinta)),
                        const TextSpan(text: ': te enviamos los datos para entrar como administrador de tu boutique (usuario '),
                        TextSpan(text: c.adminEmail, style: const TextStyle(fontWeight: FontWeight.w700, color: _tinta)),
                        const TextSpan(text: ' y una contraseña). Por seguridad, cambia la contraseña apenas inicies sesión.'),
                      ],
                    ),
                    style: GoogleFonts.inter(fontSize: 14, height: 1.5, color: _gris),
                  ),
                ),
              ],
            ),
          )
        else
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: const Color(0xFFFDECEA), borderRadius: BorderRadius.circular(10)),
            child: Text(
              'Tu boutique quedó registrada, pero no pudimos enviar el correo a ${c.correoDestino}. Escríbenos y te ayudamos con el acceso.',
              style: GoogleFonts.inter(fontSize: 14.4, color: const Color(0xFFA12A1D)),
            ),
          ),
        if (_logoDataUrl != null && !c.logoGuardado) ...[
          const SizedBox(height: 10),
          Text('No pudimos guardar tu logo; podrás subirlo después desde tu panel.',
              style: GoogleFonts.inter(fontSize: 12.8, color: const Color(0xFF9A5B12))),
        ],
        const SizedBox(height: 28),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            _botonPildora('Entrar como administrador', _irAlPanel, lleno: true),
            _botonPildora('Ver mi tienda', () => context.push('/tienda/${c.subdominio}')),
          ],
        ),
      ],
    );
  }
}

/// Selector de cualquier color (el `<input type="color">` de la web): tono,
/// saturacion y brillo, con la vista previa y su codigo.
class _SelectorColor extends StatefulWidget {
  const _SelectorColor({required this.inicial});

  final String inicial;

  @override
  State<_SelectorColor> createState() => _SelectorColorState();
}

class _SelectorColorState extends State<_SelectorColor> {
  late HSVColor _hsv = HSVColor.fromColor(_hexAColor(widget.inicial));

  Widget _deslizador(String etiqueta, double valor, double max, ValueChanged<double> onChanged) {
    return Row(
      children: [
        SizedBox(width: 74, child: Text(etiqueta, style: GoogleFonts.inter(fontSize: 13, color: _gris))),
        Expanded(
          child: Slider(value: valor, max: max, activeColor: _coral, onChanged: (v) => setState(() => onChanged(v))),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final color = _hsv.toColor();
    return AlertDialog(
      backgroundColor: _marfil,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Text('Color de tu marca', style: GoogleFonts.inter(fontSize: 17, fontWeight: FontWeight.w700, color: _tinta)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(height: 56, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(12))),
          const SizedBox(height: 8),
          Text(_colorAHex(color), style: GoogleFonts.robotoMono(fontSize: 14, color: _tinta)),
          const SizedBox(height: 8),
          _deslizador('Tono', _hsv.hue, 360, (v) => _hsv = _hsv.withHue(v)),
          _deslizador('Intensidad', _hsv.saturation, 1, (v) => _hsv = _hsv.withSaturation(v)),
          _deslizador('Brillo', _hsv.value, 1, (v) => _hsv = _hsv.withValue(v)),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text('Cancelar', style: GoogleFonts.inter(color: _gris, fontWeight: FontWeight.w600)),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_colorAHex(color)),
          style: FilledButton.styleFrom(backgroundColor: _tinta, shape: const StadiumBorder()),
          child: Text('Usar este color', style: GoogleFonts.inter(fontWeight: FontWeight.w700)),
        ),
      ],
    );
  }
}
