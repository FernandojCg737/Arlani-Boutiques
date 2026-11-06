import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import '../../models/usuario.dart';
import '../../widgets/password_strength.dart';
import '../portada/plataforma_data.dart' show colorMarca;
import 'auth_provider.dart';

// Colores del SaaS (Arlani Boutiques): azul noche, marfil y coral.
const _noche = Color(0xFF121A2C);
const _marfil = Color(0xFFF4F1EE);
const _coral = Color(0xFFE8806B);
const _gris = Color(0xFF5F6779);
const _borde = Color(0xFFE6E1DC);

/// Marca de la tienda del personal (su color y su logo) para su panel.
final marcaPersonalProvider = FutureProvider<Map<String, dynamic>?>((ref) async {
  final usuario = ref.watch(authProvider).usuario;
  if (usuario == null || usuario.isSuperAdmin || !usuario.isStaff) return null;
  final res = await ref.watch(apiClientProvider).dio.get('/mi-empresa/marca');
  return res.data as Map<String, dynamic>;
});

/// CU15 Actualizar perfil del personal: foto, nombres, apellidos y contraseña.
/// El SuperAdministrador lo ve con los colores de Arlani Boutiques (el SaaS);
/// el Administrador y los empleados, con los de su tienda.
class PerfilPersonal extends ConsumerStatefulWidget {
  const PerfilPersonal({super.key});

  @override
  ConsumerState<PerfilPersonal> createState() => _PerfilPersonalState();
}

class _PerfilPersonalState extends ConsumerState<PerfilPersonal> {
  late final TextEditingController _nombre;
  late final TextEditingController _apellidos;
  final _actual = TextEditingController();
  final _nueva = TextEditingController();
  final _confirmar = TextEditingController();
  bool _guardando = false;
  bool _cambiando = false;
  bool _subiendo = false;
  String? _okDatos, _errorDatos, _okClave, _errorClave;

  @override
  void initState() {
    super.initState();
    final (n, a) = ref.read(authProvider).usuario?.partesNombre ?? ('', '');
    _nombre = TextEditingController(text: n);
    _apellidos = TextEditingController(text: a);
  }

  @override
  void dispose() {
    for (final c in [_nombre, _apellidos, _actual, _nueva, _confirmar]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _guardar() async {
    if (_nombre.text.trim().isEmpty) {
      setState(() => _errorDatos = 'Escribe tus nombres.');
      return;
    }
    setState(() {
      _guardando = true;
      _okDatos = _errorDatos = null;
    });
    try {
      await ref.read(authProvider.notifier).updateProfile(
            nombre: _nombre.text.trim(),
            apellidos: _apellidos.text.trim().isEmpty ? null : _apellidos.text.trim(),
          );
      setState(() => _okDatos = 'Tus datos se actualizaron correctamente.');
    } catch (e) {
      setState(() => _errorDatos = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  Future<void> _cambiarClave() async {
    if (_actual.text.isEmpty) return setState(() => _errorClave = 'Ingresa tu contraseña actual.');
    if (!isPasswordValid(_nueva.text)) return setState(() => _errorClave = 'La nueva contraseña no cumple los requisitos.');
    if (_nueva.text != _confirmar.text) return setState(() => _errorClave = 'Las contraseñas no coinciden.');
    setState(() {
      _cambiando = true;
      _okClave = _errorClave = null;
    });
    try {
      await ref.read(authProvider.notifier).changePassword(actual: _actual.text, nueva: _nueva.text);
      _actual.clear();
      _nueva.clear();
      _confirmar.clear();
      setState(() => _okClave = 'Tu contraseña se actualizó. Te avisamos por correo.');
    } catch (e) {
      setState(() => _errorClave = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cambiando = false);
    }
  }

  Future<void> _foto(Future<void> Function() accion, String ok) async {
    setState(() {
      _subiendo = true;
      _okDatos = _errorDatos = null;
    });
    try {
      await accion();
      setState(() => _okDatos = ok);
    } catch (e) {
      setState(() => _errorDatos = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _subiendo = false);
    }
  }

  Future<void> _elegirFoto() async {
    final f = await ImagePicker().pickImage(source: ImageSource.gallery, maxWidth: 800, imageQuality: 85);
    if (f == null) return;
    await _foto(() => ref.read(authProvider.notifier).subirFoto(f.path, f.name), 'Tu foto de perfil se actualizó.');
  }

  void _volver(Usuario u) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(u.isSuperAdmin ? '/superadmin' : '/admin');
    }
  }

  String _rol(Usuario u, String? tienda) {
    final rol = switch (u.tipo) {
      'superadministrador' => 'SuperAdministrador',
      'administrador' => 'Administrador',
      'encargado_sucursal' => 'Encargado de sucursal',
      'cajero' => 'Cajero',
      _ => u.rol ?? '',
    };
    return u.isSuperAdmin ? '$rol · Arlani Boutiques' : (tienda != null ? '$rol · $tienda' : rol);
  }

  @override
  Widget build(BuildContext context) {
    final usuario = ref.watch(authProvider).usuario;
    if (usuario == null) return const SizedBox();
    final marca = ref.watch(marcaPersonalProvider).valueOrNull;
    // SaaS para el SuperAdministrador; la marca de su tienda para el personal.
    final principal = usuario.isSuperAdmin ? _noche : colorMarca(marca?['color_marca'] as String?);
    final acento = usuario.isSuperAdmin ? _coral : principal;
    final fondo = usuario.isSuperAdmin ? _marfil : Color.alphaBlend(principal.withValues(alpha: 0.05), const Color(0xFFF7F5F3));
    final logo = marca?['logo_url'] as String?;
    final tienda = marca?['nombre'] as String?;
    final (n, a) = usuario.partesNombre;
    final iniciales = [n, a].where((x) => x.isNotEmpty).map((x) => x[0]).join().toUpperCase();

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: fondo,
        body: ListView(padding: EdgeInsets.zero, children: [
          // Cabecera con el color de la plataforma o de la tienda.
          Container(
            color: principal,
            padding: EdgeInsets.fromLTRB(8, MediaQuery.paddingOf(context).top + 6, 8, 64),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                TextButton.icon(
                  onPressed: () => _volver(usuario),
                  style: TextButton.styleFrom(foregroundColor: Colors.white),
                  icon: const Icon(Icons.arrow_back, size: 18),
                  label: Text('VOLVER AL PANEL', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
                ),
                const Spacer(),
                if (usuario.isSuperAdmin)
                  Image.asset('assets/portada/arlani-logo-encabezado.png', height: 34)
                else if (logo != null)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: Container(
                      color: Colors.white,
                      padding: const EdgeInsets.all(3),
                      child: CachedNetworkImage(imageUrl: resolveImageUrl(logo), height: 30, fit: BoxFit.contain),
                    ),
                  ),
                IconButton(
                  tooltip: 'Cerrar sesión',
                  icon: const Icon(Icons.logout, color: Colors.white),
                  onPressed: () async {
                    await ref.read(authProvider.notifier).logout();
                    if (context.mounted) context.go('/login');
                  },
                ),
              ]),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
                child: Text('MI PERFIL',
                    style: GoogleFonts.inter(fontSize: 26, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: -0.2)),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 0),
                child: Text('Tu foto, tus datos y tu contraseña.',
                    style: GoogleFonts.inter(fontSize: 13.5, color: Colors.white.withValues(alpha: 0.78))),
              ),
            ]),
          ),
          Transform.translate(
            offset: const Offset(0, -44),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                // Tarjeta con la foto.
                _Tarjeta(
                  child: Column(children: [
                    Stack(clipBehavior: Clip.none, children: [
                      CircleAvatar(
                        radius: 46,
                        backgroundColor: principal,
                        backgroundImage: usuario.fotoUrl != null ? CachedNetworkImageProvider(usuario.fotoUrl!) : null,
                        child: usuario.fotoUrl == null
                            ? Text(iniciales, style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w800))
                            : null,
                      ),
                      Positioned(
                        right: -4,
                        bottom: -4,
                        child: Material(
                          color: acento,
                          shape: const CircleBorder(side: BorderSide(color: Colors.white, width: 3)),
                          child: InkWell(
                            customBorder: const CircleBorder(),
                            onTap: _subiendo ? null : _elegirFoto,
                            child: Padding(
                              padding: const EdgeInsets.all(8),
                              child: _subiendo
                                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                                  : const Icon(Icons.photo_camera, size: 16, color: Colors.white),
                            ),
                          ),
                        ),
                      ),
                    ]),
                    const SizedBox(height: 12),
                    Text(usuario.nombre, textAlign: TextAlign.center,
                        style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w800, color: _noche)),
                    Text(usuario.email, style: GoogleFonts.inter(fontSize: 13, color: _gris)),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(color: principal.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(20)),
                      child: Text(_rol(usuario, tienda),
                          style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, color: principal)),
                    ),
                    if (usuario.fotoUrl != null && !_subiendo)
                      TextButton(
                        onPressed: () => _foto(() => ref.read(authProvider.notifier).quitarFoto(), 'Quitamos tu foto de perfil.'),
                        child: const Text('Quitar foto', style: TextStyle(color: Color(0xFFB3261E))),
                      ),
                    Text('JPG, PNG o WEBP · hasta 10 MB', style: GoogleFonts.inter(fontSize: 11, color: _gris)),
                  ]),
                ),
                const SizedBox(height: 16),
                _Tarjeta(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    _Titulo('Datos personales', principal),
                    if (_errorDatos != null) _Mensaje(_errorDatos!, error: true),
                    if (_okDatos != null) _Mensaje(_okDatos!),
                    _Campo(controller: _nombre, etiqueta: 'Nombres', color: principal),
                    _Campo(controller: _apellidos, etiqueta: 'Apellidos', color: principal),
                    _Campo(controller: TextEditingController(text: usuario.email), etiqueta: 'Correo', color: principal, habilitado: false),
                    const SizedBox(height: 6),
                    _Boton(_guardando ? 'GUARDANDO...' : 'GUARDAR CAMBIOS', principal, _guardando ? null : _guardar),
                  ]),
                ),
                const SizedBox(height: 16),
                _Tarjeta(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    _Titulo('Cambiar contraseña', principal),
                    if (_errorClave != null) _Mensaje(_errorClave!, error: true),
                    if (_okClave != null) _Mensaje(_okClave!),
                    _Campo(controller: _actual, etiqueta: 'Contraseña actual', color: principal, oculto: true),
                    _Campo(
                      controller: _nueva,
                      etiqueta: 'Nueva contraseña',
                      color: principal,
                      oculto: true,
                      onChanged: (_) => setState(() {}),
                    ),
                    PasswordStrengthChecklist(password: _nueva.text),
                    const SizedBox(height: 8),
                    _Campo(controller: _confirmar, etiqueta: 'Confirmar contraseña', color: principal, oculto: true),
                    const SizedBox(height: 6),
                    _Boton(_cambiando ? 'ACTUALIZANDO...' : 'CAMBIAR CONTRASEÑA', principal, _cambiando ? null : _cambiarClave),
                  ]),
                ),
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}

class _Tarjeta extends StatelessWidget {
  const _Tarjeta({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _borde),
          boxShadow: const [BoxShadow(color: Color(0x14121A2C), blurRadius: 18, offset: Offset(0, 6))],
        ),
        child: child,
      );
}

class _Titulo extends StatelessWidget {
  const _Titulo(this.texto, this.color);
  final String texto;
  final Color color;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Text(texto, style: GoogleFonts.inter(fontSize: 17, fontWeight: FontWeight.w800, color: color)),
      );
}

class _Mensaje extends StatelessWidget {
  const _Mensaje(this.texto, {this.error = false});
  final String texto;
  final bool error;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: error ? const Color(0xFFFDECEA) : const Color(0xFFEAF6EC),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(texto, style: TextStyle(fontSize: 13, color: error ? const Color(0xFFB3261E) : const Color(0xFF2E7D32))),
      );
}

class _Campo extends StatelessWidget {
  const _Campo({
    required this.controller,
    required this.etiqueta,
    required this.color,
    this.oculto = false,
    this.habilitado = true,
    this.onChanged,
  });

  final TextEditingController controller;
  final String etiqueta;
  final Color color;
  final bool oculto;
  final bool habilitado;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: TextField(
          controller: controller,
          obscureText: oculto,
          enabled: habilitado,
          onChanged: onChanged,
          style: GoogleFonts.inter(fontSize: 15, color: _noche),
          decoration: InputDecoration(
            labelText: etiqueta,
            labelStyle: GoogleFonts.inter(color: _gris),
            floatingLabelStyle: GoogleFonts.inter(color: color, fontWeight: FontWeight.w700),
            filled: true,
            fillColor: habilitado ? const Color(0xFFFAF9F7) : const Color(0xFFF0EEEB),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: _borde)),
            enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: _borde)),
            focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: color, width: 1.6)),
          ),
        ),
      );
}

class _Boton extends StatelessWidget {
  const _Boton(this.texto, this.color, this.onTap);
  final String texto;
  final Color color;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => FilledButton(
        onPressed: onTap,
        style: FilledButton.styleFrom(
          backgroundColor: color,
          disabledBackgroundColor: color.withValues(alpha: 0.5),
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(50),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          textStyle: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w800, letterSpacing: 0.8),
        ),
        child: Text(texto),
      );
}
