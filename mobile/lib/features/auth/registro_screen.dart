import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_client.dart';
import '../../widgets/password_strength.dart';
import 'auth_provider.dart';
import 'google_auth.dart';
import 'google_auth_button.dart';

/// "Crear una cuenta": el mismo `pages/registro` de la web en celular (y el
/// mismo diseño que el login de la app): marca de agua de Arlani, campos
/// subrayados, la lista de requisitos de la contraseña y Google. Usa los
/// mismos endpoints que la web (`/auth/register` y `/auth/google`).
class RegistroScreen extends ConsumerStatefulWidget {
  const RegistroScreen({super.key, this.onSuccess, this.onIrALogin});

  /// Igual que en LoginScreen: si se abrio empujada desde una accion que
  /// necesitaba sesion (carrito, reservar, probador AR), al registrarse
  /// vuelve y retoma esa accion en vez de ir al inicio.
  final VoidCallback? onSuccess;

  /// "Ya tienes cuenta? Inicia sesion" cuando esta pantalla se abrio fuera
  /// del router (ver `asegurarSesion`); por defecto va al login.
  final VoidCallback? onIrALogin;

  @override
  ConsumerState<RegistroScreen> createState() => _RegistroScreenState();
}

class _RegistroScreenState extends ConsumerState<RegistroScreen> {
  final _nombreCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _telefonoCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();
  final _passwordFoco = FocusNode();
  bool _verPassword = false;
  bool _verConfirmacion = false;
  // La lista de requisitos aparece al tocar la contraseña (como en la web).
  bool _passwordTocada = false;
  bool _loading = false;
  bool _loadingGoogle = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _passwordFoco.addListener(() {
      if (_passwordFoco.hasFocus && !_passwordTocada) setState(() => _passwordTocada = true);
    });
  }

  @override
  void dispose() {
    _nombreCtrl.dispose();
    _emailCtrl.dispose();
    _telefonoCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmCtrl.dispose();
    _passwordFoco.dispose();
    super.dispose();
  }

  // Mismas validaciones y mensajes que `registro.ts`.
  Future<void> _submit() async {
    setState(() => _passwordTocada = true);
    if (_nombreCtrl.text.trim().isEmpty || _emailCtrl.text.trim().isEmpty || _passwordCtrl.text.isEmpty) {
      setState(() => _error = 'Completa nombre, correo y contraseña.');
      return;
    }
    if (!isPasswordValid(_passwordCtrl.text)) {
      setState(() => _error = 'La contraseña no cumple los requisitos mínimos.');
      return;
    }
    if (_passwordCtrl.text != _confirmCtrl.text) {
      setState(() => _error = 'Las contraseñas no coinciden.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authProvider.notifier).register(
        nombre: _nombreCtrl.text.trim(),
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
        telefono: _telefonoCtrl.text.trim().isEmpty ? null : _telefonoCtrl.text.trim(),
      );
      if (!mounted) return;
      _irDespuesDeEntrar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _irDespuesDeEntrar() {
    if (widget.onSuccess != null) {
      widget.onSuccess!();
    } else {
      context.go('/');
    }
  }

  Future<void> _registrarseConGoogle() async {
    setState(() {
      _loadingGoogle = true;
      _error = null;
    });
    try {
      final resultado = await signInWithGoogle();
      if (resultado.cancelled) return;
      await ref.read(authProvider.notifier).loginWithGoogle(resultado.idToken!);
      if (!mounted) return;
      _irDespuesDeEntrar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loadingGoogle = false);
    }
  }

  void _irALogin() {
    if (widget.onIrALogin != null) {
      widget.onIrALogin!();
    } else if (context.canPop()) {
      context.pop();
    } else {
      context.go('/login');
    }
  }

  static const _tinta = Color(0xFF121A2C);
  static const _gris = Color(0xFF999999);
  static const _texto = Color(0xFF777777);
  static const _linea = Color(0xFFDDDDDD);

  static final _etiqueta = GoogleFonts.inter(fontSize: 11, letterSpacing: 0.66, fontWeight: FontWeight.w700, color: _gris);

  InputDecoration _campo(String pista, {Widget? sufijo}) => InputDecoration(
        hintText: pista,
        hintStyle: GoogleFonts.inter(color: const Color(0xFFBBBBBB), fontSize: 15),
        suffixIcon: sufijo,
        filled: false,
        isDense: true,
        contentPadding: const EdgeInsets.only(top: 6, bottom: 10),
        border: const UnderlineInputBorder(borderSide: BorderSide(color: _linea)),
        enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: _linea)),
        focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: _tinta)),
      );

  Widget _ojo(bool visible, VoidCallback onTap, String descripcion) => IconButton(
        tooltip: descripcion,
        icon: Icon(visible ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 19, color: _gris),
        onPressed: onTap,
      );

  Widget _grupo(String etiqueta, Widget campo, {Widget? debajo}) => Padding(
        padding: const EdgeInsets.only(bottom: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(etiqueta.toUpperCase(), style: _etiqueta),
            const SizedBox(height: 2),
            campo,
            ?debajo,
          ],
        ),
      );

  /// `.password-checklist`: dos columnas con un punto rojo o verde.
  Widget _requisitos() {
    final texto = _passwordCtrl.text;
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: LayoutBuilder(
        builder: (context, c) => Wrap(
          spacing: 12,
          runSpacing: 4,
          children: [
            for (final regla in passwordRules)
              SizedBox(
                width: (c.maxWidth - 12) / 2,
                child: Row(
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: regla.test(texto) ? const Color(0xFF2E7D32) : const Color(0xFFB3261E),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        _conTildes(regla.label),
                        style: GoogleFonts.inter(
                          fontSize: 11,
                          color: regla.test(texto) ? const Color(0xFF2E7D32) : const Color(0xFFB3261E),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  static String _conTildes(String s) => s
      .replaceAll('Minimo', 'Mínimo')
      .replaceAll('mayuscula', 'mayúscula')
      .replaceAll('minuscula', 'minúscula')
      .replaceAll('numero', 'número')
      .replaceAll('caracter', 'carácter');

  Widget _ventaja(String titulo, String detalle) => Expanded(
        child: Column(
          children: [
            Text(titulo, style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: _tinta)),
            const SizedBox(height: 2),
            Text(detalle.toUpperCase(),
                style: GoogleFonts.inter(fontSize: 10, letterSpacing: 0.6, color: _gris, fontWeight: FontWeight.w700)),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final volver = widget.onSuccess != null ? () => Navigator.of(context).pop() : () => context.go('/');
    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        children: [
          // Marca de agua de Arlani detras del formulario (como en la web).
          Positioned.fill(
            child: IgnorePointer(
              child: Center(
                child: Opacity(
                  opacity: 0.05,
                  child: Transform.rotate(angle: -0.1, child: Image.asset('assets/arlani_marca_agua.png', width: 520)),
                ),
              ),
            ),
          ),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 20, 24, 28),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 380),
                  child: AutofillGroup(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton.icon(
                            onPressed: volver,
                            style: TextButton.styleFrom(foregroundColor: _gris, padding: EdgeInsets.zero),
                            icon: const Icon(Icons.arrow_back, size: 15),
                            label: Text(widget.onSuccess != null ? 'VOLVER' : 'VOLVER AL INICIO', style: _etiqueta),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Image.asset('assets/arlani_logo_claro.png', height: 60, semanticLabel: 'Arlani Boutiques'),
                        ),
                        const SizedBox(height: 28),
                        Row(
                          children: [
                            Container(width: 24, height: 1, color: const Color(0xFFCCCCCC)),
                            const SizedBox(width: 10),
                            Text('REGISTRO', style: _etiqueta.copyWith(letterSpacing: 1.3)),
                          ],
                        ),
                        const SizedBox(height: 14),
                        Text(
                          'CREAR UNA CUENTA',
                          style: GoogleFonts.bricolageGrotesque(
                            fontSize: 28,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.28,
                            color: _tinta,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Regístrate para guardar tus datos, ver tus pedidos y agilizar tus compras.',
                          style: GoogleFonts.inter(fontSize: 14, height: 1.6, color: _texto),
                        ),
                        const SizedBox(height: 32),
                        if (_error != null)
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                            margin: const EdgeInsets.only(bottom: 20),
                            color: const Color(0xFFFDECEA),
                            child: Text(_error!, style: GoogleFonts.inter(color: const Color(0xFFB3261E), fontSize: 13)),
                          ),
                        _grupo(
                          'Nombre completo',
                          TextField(
                            controller: _nombreCtrl,
                            textCapitalization: TextCapitalization.words,
                            textInputAction: TextInputAction.next,
                            autofillHints: const [AutofillHints.name],
                            style: GoogleFonts.inter(fontSize: 15, color: _tinta),
                            decoration: _campo('Introduce tu nombre'),
                          ),
                        ),
                        _grupo(
                          'Correo electrónico',
                          TextField(
                            controller: _emailCtrl,
                            keyboardType: TextInputType.emailAddress,
                            textInputAction: TextInputAction.next,
                            autofillHints: const [AutofillHints.email],
                            style: GoogleFonts.inter(fontSize: 15, color: _tinta),
                            decoration: _campo('Introduce tu email'),
                          ),
                        ),
                        _grupo(
                          'Teléfono',
                          TextField(
                            controller: _telefonoCtrl,
                            keyboardType: TextInputType.phone,
                            textInputAction: TextInputAction.next,
                            autofillHints: const [AutofillHints.telephoneNumber],
                            style: GoogleFonts.inter(fontSize: 15, color: _tinta),
                            decoration: _campo('Introduce tu teléfono'),
                          ),
                        ),
                        _grupo(
                          'Contraseña',
                          TextField(
                            controller: _passwordCtrl,
                            focusNode: _passwordFoco,
                            obscureText: !_verPassword,
                            textInputAction: TextInputAction.next,
                            autofillHints: const [AutofillHints.newPassword],
                            onChanged: (_) => setState(() {}),
                            style: GoogleFonts.inter(fontSize: 15, color: _tinta),
                            decoration: _campo(
                              '••••••••',
                              sufijo: _ojo(
                                _verPassword,
                                () => setState(() => _verPassword = !_verPassword),
                                _verPassword ? 'Ocultar contraseña' : 'Mostrar contraseña',
                              ),
                            ),
                          ),
                          debajo: _passwordTocada ? _requisitos() : null,
                        ),
                        _grupo(
                          'Confirmar contraseña',
                          TextField(
                            controller: _confirmCtrl,
                            obscureText: !_verConfirmacion,
                            textInputAction: TextInputAction.done,
                            onSubmitted: (_) => _loading ? null : _submit(),
                            style: GoogleFonts.inter(fontSize: 15, color: _tinta),
                            decoration: _campo(
                              '••••••••',
                              sufijo: _ojo(
                                _verConfirmacion,
                                () => setState(() => _verConfirmacion = !_verConfirmacion),
                                _verConfirmacion ? 'Ocultar contraseña' : 'Mostrar contraseña',
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        SizedBox(
                          height: 50,
                          child: FilledButton(
                            onPressed: _loading ? null : _submit,
                            style: FilledButton.styleFrom(
                              backgroundColor: _tinta,
                              disabledBackgroundColor: _tinta.withValues(alpha: 0.6),
                              foregroundColor: Colors.white,
                              disabledForegroundColor: Colors.white,
                              shape: const StadiumBorder(),
                              textStyle: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.8),
                            ),
                            child: Text(_loading ? 'CREANDO CUENTA...' : 'CREAR CUENTA'),
                          ),
                        ),
                        const SizedBox(height: 24),
                        Row(
                          children: [
                            const Expanded(child: Divider(color: Color(0xFFEEEEEE))),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 12),
                              child: Text('O', style: GoogleFonts.inter(fontSize: 12, color: const Color(0xFFBBBBBB))),
                            ),
                            const Expanded(child: Divider(color: Color(0xFFEEEEEE))),
                          ],
                        ),
                        const SizedBox(height: 24),
                        GoogleAuthButton(
                          label: 'Registrarte con Google',
                          loading: _loadingGoogle,
                          onPressed: _loading ? null : _registrarseConGoogle,
                        ),
                        const SizedBox(height: 28),
                        Wrap(
                          alignment: WrapAlignment.center,
                          children: [
                            Text('¿Ya tienes cuenta? ', style: GoogleFonts.inter(fontSize: 13, color: _texto)),
                            GestureDetector(
                              onTap: _irALogin,
                              child: Text(
                                'Inicia sesión aquí',
                                style: GoogleFonts.inter(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                  color: _tinta,
                                  decoration: TextDecoration.underline,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 32),
                        const Divider(color: Color(0xFFEEEEEE), height: 1),
                        const SizedBox(height: 24),
                        Row(
                          children: [
                            _ventaja('Tienda', 'Online'),
                            _ventaja('Caja', 'Sin internet'),
                            _ventaja('Probador', 'Virtual'),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
