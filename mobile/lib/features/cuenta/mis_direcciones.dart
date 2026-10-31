import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import 'cuenta_repository.dart';
import 'estilo_cuenta.dart';

/// Centro por defecto del mapa: Santa Cruz (igual que `CENTRO_POR_DEFECTO`).
const _centro = LatLng(-17.7833, -63.1821);
const _aliasRapidos = ['Casa', 'Trabajo', 'Casa de mis papás'];

/// "Mis direcciones" (componente `mis-direcciones` de la web): a donde quiere
/// el cliente que le envien sus compras, con la ubicacion en el mapa.
class MisDirecciones extends ConsumerStatefulWidget {
  const MisDirecciones({super.key});

  @override
  ConsumerState<MisDirecciones> createState() => _MisDireccionesState();
}

class _MisDireccionesState extends ConsumerState<MisDirecciones> {
  List<DireccionCliente>? _direcciones;
  String? _aviso;
  bool _avisoError = false;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final d = await ref.read(cuentaRepositoryProvider).direcciones();
      if (mounted) setState(() => _direcciones = d);
    } catch (_) {
      if (mounted) setState(() => _direcciones = []);
    }
  }

  Future<void> _abrirFormulario([DireccionCliente? editando]) async {
    final guardada = await abrirHojaCuenta<DireccionCliente>(
      context,
      titulo: editando == null ? 'Nueva dirección de envío' : 'Editar dirección',
      subtitulo: 'Marca en el mapa dónde quieres recibir tu pedido.',
      cuerpo: (_) => FormularioDireccion(editando: editando),
    );
    if (guardada == null || !mounted) return;
    setState(() {
      _avisoError = false;
      _aviso = editando == null ? 'Dirección guardada: ya puedes elegirla al pagar.' : 'Dirección actualizada.';
    });
    await _cargar();
  }

  Future<void> _borrar(DireccionCliente d) async {
    if (!await confirmarCuenta(context, '¿Borrar la dirección "${d.alias}"? Tus compras ya hechas no cambian.', si: 'Borrar')) {
      return;
    }
    try {
      await ref.read(cuentaRepositoryProvider).borrarDireccion(d.id);
      await _cargar();
    } catch (e) {
      if (mounted) {
        setState(() {
          _avisoError = true;
          _aviso = extractErrorMessage(e);
        });
      }
    }
  }

  Future<void> _predeterminar(DireccionCliente d) async {
    try {
      await ref.read(cuentaRepositoryProvider).guardarDireccion({
        'alias': d.alias,
        'direccion': d.direccion,
        'referencia': d.referencia,
        'ciudad': d.ciudad,
        'latitud': d.latitud.toStringAsFixed(6),
        'longitud': d.longitud.toStringAsFixed(6),
        'predeterminada': true,
      }, id: d.id);
      await _cargar();
    } catch (e) {
      if (mounted) {
        setState(() {
          _avisoError = true;
          _aviso = extractErrorMessage(e);
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final direcciones = _direcciones;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Guarda a dónde quieres que te envíen tus compras. Al pagar eliges “Envío a domicilio” y una de estas direcciones.',
          style: GoogleFonts.inter(fontSize: 13, height: 1.5, color: grisOscuroCuenta),
        ),
        const SizedBox(height: 14),
        Align(alignment: Alignment.centerLeft, child: BotonCuenta('+ Agregar dirección', onTap: () => _abrirFormulario())),
        const SizedBox(height: 18),
        if (_aviso != null) AvisoCuenta(_aviso!, error: _avisoError),
        if (direcciones == null)
          cargandoCuenta()
        else if (direcciones.isEmpty)
          vacioCuenta('Todavía no guardaste direcciones.')
        else
          for (final d in direcciones) ...[
            TarjetaCuenta(
              padding: EdgeInsets.zero,
              destacada: d.predeterminada,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SizedBox(height: 140, child: MapaUbicacion(punto: LatLng(d.latitud, d.longitud), soloLectura: true)),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: 8,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Text(d.alias, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: tintaCuenta)),
                            if (d.predeterminada) const InsigniaEstado(texto: 'Predeterminada', tono: TonoEstado.ok),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text('${d.direccion}${d.ciudad != null ? ', ${d.ciudad}' : ''}',
                            style: GoogleFonts.inter(fontSize: 13, height: 1.4, color: grisOscuroCuenta)),
                        if (d.referencia != null && d.referencia!.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(d.referencia!, style: GoogleFonts.inter(fontSize: 12, color: grisCuenta)),
                        ],
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 16,
                          children: [
                            EnlaceCuenta('Editar', onTap: () => _abrirFormulario(d)),
                            if (!d.predeterminada) EnlaceCuenta('Usar por defecto', onTap: () => _predeterminar(d)),
                            EnlaceCuenta(
                              'Ver en el mapa',
                              onTap: () => launchUrl(
                                Uri.parse(
                                  'https://www.openstreetmap.org/?mlat=${d.latitud}&mlon=${d.longitud}#map=17/${d.latitud}/${d.longitud}',
                                ),
                                mode: LaunchMode.externalApplication,
                              ),
                            ),
                            EnlaceCuenta('Borrar', peligro: true, onTap: () => _borrar(d)),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],
      ],
    );
  }
}

/// Mapa de OpenStreetMap con un pin (`app-mapa-ubicacion`): solo lectura en
/// las tarjetas; en el formulario, tocar el mapa mueve el pin.
class MapaUbicacion extends StatelessWidget {
  const MapaUbicacion({super.key, required this.punto, this.soloLectura = false, this.onCambio, this.controller});

  final LatLng? punto;
  final bool soloLectura;
  final ValueChanged<LatLng>? onCambio;
  final MapController? controller;

  @override
  Widget build(BuildContext context) {
    return FlutterMap(
      mapController: controller,
      options: MapOptions(
        initialCenter: punto ?? _centro,
        initialZoom: punto == null ? 13 : 16,
        interactionOptions: InteractionOptions(flags: soloLectura ? InteractiveFlag.none : InteractiveFlag.all & ~InteractiveFlag.rotate),
        onTap: soloLectura ? null : (_, p) => onCambio?.call(p),
      ),
      children: [
        TileLayer(urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', userAgentPackageName: 'com.atelieraranier.mobile_app'),
        if (punto != null)
          MarkerLayer(
            markers: [
              Marker(
                point: punto!,
                width: 40,
                height: 40,
                alignment: Alignment.topCenter,
                child: const Icon(Icons.location_on, size: 40, color: Color(0xFFC4503D)),
              ),
            ],
          ),
      ],
    );
  }
}

/// Formulario de una direccion (nueva o editada), con el mapa.
class FormularioDireccion extends ConsumerStatefulWidget {
  const FormularioDireccion({super.key, this.editando});

  final DireccionCliente? editando;

  @override
  ConsumerState<FormularioDireccion> createState() => _FormularioDireccionState();
}

class _FormularioDireccionState extends ConsumerState<FormularioDireccion> {
  final _mapa = MapController();
  late final _alias = TextEditingController(text: widget.editando?.alias ?? 'Casa');
  late final _direccion = TextEditingController(text: widget.editando?.direccion ?? '');
  late final _referencia = TextEditingController(text: widget.editando?.referencia ?? '');
  late final _ciudad = TextEditingController(text: widget.editando?.ciudad ?? '');
  late LatLng? _punto = widget.editando == null ? null : LatLng(widget.editando!.latitud, widget.editando!.longitud);
  late bool _predeterminada = widget.editando?.predeterminada ?? false;
  // El texto lo sugiere el mapa hasta que el cliente lo escribe a mano.
  late bool _textoManual = widget.editando != null;
  bool _ubicando = false;
  bool _guardando = false;
  String? _error;

  @override
  void dispose() {
    _alias.dispose();
    _direccion.dispose();
    _referencia.dispose();
    _ciudad.dispose();
    super.dispose();
  }

  Future<void> _moverPin(LatLng p) async {
    setState(() => _punto = p);
    if (_textoManual) return;
    // Calle aproximada (OpenStreetMap Nominatim), como `direccionDe` en la web.
    try {
      final res = await Dio().get(
        'https://nominatim.openstreetmap.org/reverse',
        queryParameters: {'format': 'jsonv2', 'accept-language': 'es', 'lat': p.latitude, 'lon': p.longitude},
        options: Options(headers: {'User-Agent': 'ArlaniBoutiques/1.0 (app movil)'}),
      );
      final d = res.data as Map<String, dynamic>;
      final a = (d['address'] as Map<String, dynamic>?) ?? {};
      final calle = [a['road'], a['house_number']].whereType<String>().join(' ');
      final zona = (a['suburb'] ?? a['neighbourhood'] ?? a['quarter'] ?? '') as String;
      final texto = [calle, zona].where((s) => s.isNotEmpty).join(', ');
      if (!mounted || _textoManual) return;
      setState(() {
        _direccion.text = texto.isNotEmpty ? texto : (d['display_name'] as String? ?? '');
        final ciudad = a['city'] ?? a['town'] ?? a['village'];
        if (ciudad is String) _ciudad.text = ciudad;
      });
    } catch (_) {
      // Sin sugerencia: el cliente la escribe.
    }
  }

  Future<void> _usarMiUbicacion() async {
    setState(() {
      _ubicando = true;
      _error = null;
    });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) throw 'Activa la ubicación del teléfono o mueve el pin en el mapa.';
      var permiso = await Geolocator.checkPermission();
      if (permiso == LocationPermission.denied) permiso = await Geolocator.requestPermission();
      if (permiso == LocationPermission.denied || permiso == LocationPermission.deniedForever) {
        throw 'No diste permiso para usar tu ubicación. Toca el mapa para marcarla.';
      }
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 12)),
      );
      final p = LatLng(pos.latitude, pos.longitude);
      _mapa.move(p, 17);
      await _moverPin(p);
    } catch (e) {
      if (mounted) setState(() => _error = e is String ? e : 'No pudimos obtener tu ubicación. Toca el mapa para marcarla.');
    } finally {
      if (mounted) setState(() => _ubicando = false);
    }
  }

  Future<void> _guardar() async {
    final p = _punto;
    if (p == null) {
      setState(() => _error = 'Marca tu ubicación en el mapa (usa tu GPS o toca el mapa).');
      return;
    }
    if (_alias.text.trim().length < 2 || _direccion.text.trim().length < 5) {
      setState(() => _error = 'Ponle un nombre y escribe la dirección (calle y número o zona).');
      return;
    }
    setState(() {
      _guardando = true;
      _error = null;
    });
    try {
      final d = await ref.read(cuentaRepositoryProvider).guardarDireccion({
        'alias': _alias.text.trim(),
        'direccion': _direccion.text.trim(),
        'referencia': _referencia.text.trim().isEmpty ? null : _referencia.text.trim(),
        'ciudad': _ciudad.text.trim().isEmpty ? null : _ciudad.text.trim(),
        'latitud': p.latitude.toStringAsFixed(6),
        'longitud': p.longitude.toStringAsFixed(6),
        'predeterminada': _predeterminada,
      }, id: widget.editando?.id);
      if (mounted) Navigator.of(context).pop(d);
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  Widget _campo(String etiqueta, TextEditingController ctrl, {String? pista, ValueChanged<String>? onChanged}) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (etiqueta.isNotEmpty) etiquetaCampo(etiqueta),
            TextField(
              controller: ctrl,
              onChanged: onChanged,
              style: GoogleFonts.inter(fontSize: 14.5, color: tintaCuenta),
              decoration: decoracionCampo(pista: pista),
            ),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 230,
            child: Stack(
              children: [
                MapaUbicacion(punto: _punto, controller: _mapa, onCambio: _moverPin),
                Positioned(
                  right: 8,
                  bottom: 8,
                  child: FilledButton.icon(
                    onPressed: _ubicando ? null : _usarMiUbicacion,
                    icon: _ubicando
                        ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.my_location, size: 16),
                    label: Text('Usar mi ubicación', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700)),
                    style: FilledButton.styleFrom(backgroundColor: tintaCuenta, shape: const StadiumBorder()),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(top: 6, bottom: 16),
            child: Text('Toca el mapa para mover el pin al lugar exacto.', style: GoogleFonts.inter(fontSize: 12, color: grisCuenta)),
          ),
          etiquetaCampo('Nombre de la dirección'),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final a in _aliasRapidos)
                ChoiceChip(
                  label: Text(a, style: GoogleFonts.inter(fontSize: 12.5)),
                  selected: _alias.text == a,
                  showCheckmark: false,
                  selectedColor: tintaCuenta,
                  labelStyle: TextStyle(color: _alias.text == a ? Colors.white : tintaCuenta),
                  shape: const StadiumBorder(side: BorderSide(color: Color(0xFFDDDDDD))),
                  onSelected: (_) => setState(() => _alias.text = a),
                ),
            ],
          ),
          const SizedBox(height: 8),
          _campo('', _alias, onChanged: (_) => setState(() {})),
          _campo('Dirección (calle, número, zona)', _direccion,
              pista: 'Ej. Av. Banzer 3er anillo, calle 2 #15', onChanged: (_) => _textoManual = true),
          _campo('Referencia para el repartidor (opcional)', _referencia, pista: 'Ej. Portón negro, frente a la farmacia'),
          _campo('Ciudad', _ciudad),
          CheckboxListTile(
            value: _predeterminada,
            onChanged: (v) => setState(() => _predeterminada = v ?? false),
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            activeColor: tintaCuenta,
            title: Text('Usar esta dirección por defecto', style: GoogleFonts.inter(fontSize: 13.5, color: tintaCuenta)),
          ),
          if (_error != null) ...[const SizedBox(height: 8), AvisoCuenta(_error!, error: true)],
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(child: BotonCuenta('Cancelar', lleno: false, ancho: true, onTap: () => Navigator.of(context).pop())),
              const SizedBox(width: 10),
              Expanded(
                child: BotonCuenta(_guardando ? 'Guardando…' : 'Guardar dirección', ancho: true, onTap: _guardando ? null : _guardar),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
