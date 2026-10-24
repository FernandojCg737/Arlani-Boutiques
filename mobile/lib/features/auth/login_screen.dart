import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import 'auth_provider.dart';
import 'google_auth.dart';
import 'google_auth_button.dart';
import 'registro_screen.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key, this.onSuccess});

  /// Si esta pantalla se abrio empujada (push) desde una accion que
  /// necesitaba sesion (agregar al carrito, reservar, probarse una prenda),
  /// el llamador pasa esto para volver (pop) y retomar esa misma accion en
  /// vez del comportamiento por defecto de ir a Home/Admin -- asi el
  /// cliente no pierde lo que estaba haciendo (reportado por testers).
  final VoidCallback? onSuccess;

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  bool _loadingGoogle = false;
  String? _error;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_emailCtrl.text.trim().isEmpty || _passwordCtrl.text.isEmpty) {
      setState(() => _error = 'Completa correo y contrasena.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authProvider.notifier).login(email: _emailCtrl.text.trim(), password: _passwordCtrl.text);
      if (!mounted) return;
      if (widget.onSuccess != null) {
        widget.onSuccess!();
      } else {
        final auth = ref.read(authProvider);
        context.go(auth.isStaff ? '/admin' : '/');
      }
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _continuarConGoogle() async {
    setState(() {
      _loadingGoogle = true;
      _error = null;
    });
    try {
      final resultado = await signInWithGoogle();
      if (resultado.cancelled) return;
      await ref.read(authProvider.notifier).loginWithGoogle(resultado.idToken!);
      if (!mounted) return;
      if (widget.onSuccess != null) {
        widget.onSuccess!();
      } else {
        final auth = ref.read(authProvider);
        context.go(auth.isStaff ? '/admin' : '/');
      }
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loadingGoogle = false);
    }
  }

  // Si esta pantalla vino de una accion que pedia sesion, el registro
  // tambien tiene que volver a esa accion: se abre empujado (no por el
  // router) y, al registrarse, cierra registro + login y llama a onSuccess.
  void _irARegistro() {
    final onSuccess = widget.onSuccess;
    if (onSuccess == null) {
      context.push('/registro');
      return;
    }
    final navigator = Navigator.of(context);
    navigator.push(
      MaterialPageRoute(
        builder: (_) => RegistroScreen(
          onSuccess: () {
            navigator.pop();
            onSuccess();
          },
          onIrALogin: () => navigator.pop(),
        ),
      ),
    );
  }

  // Mismo diseño que el login de la web (version celular): fondo claro con la
  // marca de agua de Arlani, campos subrayados y botones redondeados.
  static const _tinta = Color(0xFF121A2C);
  static const _gris = Color(0xFF6B6B6B);
  static const _linea = Color(0xFFE2E2E2);

  static const _etiqueta = TextStyle(fontSize: 11, letterSpacing: 1.4, fontWeight: FontWeight.w700, color: _gris);

  InputDecoration _campo(String pista, {Widget? sufijo}) => InputDecoration(
        hintText: pista,
        hintStyle: const TextStyle(color: Color(0xFFAAAAAA), fontSize: 15),
        suffixIcon: sufijo,
        filled: false,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        border: const UnderlineInputBorder(borderSide: BorderSide(color: _linea)),
        enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: _linea)),
        focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: _tinta, width: 1.4)),
      );

  Widget _ventaja(String titulo, String detalle) => Expanded(
        child: Column(
          children: [
            Text(titulo, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: _tinta)),
            const SizedBox(height: 2),
            Text(detalle, style: const TextStyle(fontSize: 9, letterSpacing: 1.2, color: _gris, fontWeight: FontWeight.w600)),
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
                  child: Transform.rotate(angle: -0.12, child: Image.asset('assets/arlani_marca_agua.png', width: 520)),
                ),
              ),
            ),
          ),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(28, 20, 28, 24),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 440),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: volver,
                          style: TextButton.styleFrom(foregroundColor: _gris, padding: EdgeInsets.zero),
                          icon: const Icon(Icons.arrow_back, size: 16),
                          label: Text(widget.onSuccess != null ? 'VOLVER' : 'VOLVER AL INICIO', style: _etiqueta),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Image.asset('assets/arlani_logo_claro.png', height: 64, semanticLabel: 'Arlani Boutiques'),
                      ),
                      const SizedBox(height: 26),
                      const Row(
                        children: [
                          SizedBox(width: 24, child: Divider(color: _linea, thickness: 1)),
                          SizedBox(width: 10),
                          Text('ACCESO', style: _etiqueta),
                        ],
                      ),
                      const SizedBox(height: 12),
                      const Text('INICIAR SESIÓN', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w500, color: _tinta)),
                      const SizedBox(height: 12),
                      const Text(
                        'Accede a tu cuenta para gestionar pedidos y explorar el catálogo.',
                        style: TextStyle(fontSize: 15, height: 1.5, color: Color(0xFF555555)),
                      ),
                      const SizedBox(height: 26),
                      if (_error != null)
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          margin: const EdgeInsets.only(bottom: 16),
                          color: const Color(0xFFFDECEA),
                          child: Text(_error!, style: const TextStyle(color: Color(0xFFB3261E), fontSize: 13)),
                        ),
                      const Text('CORREO ELECTRÓNICO', style: _etiqueta),
                      TextField(
                        controller: _emailCtrl,
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.email],
                        decoration: _campo('Introduce tu email'),
                      ),
                      const SizedBox(height: 26),
                      Row(
                        children: [
                          const Expanded(child: Text('CONTRASEÑA', style: _etiqueta)),
                          GestureDetector(
                            onTap: () => context.push('/recuperar'),
                            child: const Text(
                              '¿Olvidaste tu contraseña?',
                              style: TextStyle(
                                fontSize: 11, fontWeight: FontWeight.w700, color: _tinta, decoration: TextDecoration.underline,
                              ),
                            ),
                          ),
                        ],
                      ),
                      TextField(
                        controller: _passwordCtrl,
                        obscureText: _obscure,
                        autofillHints: const [AutofillHints.password],
                        onSubmitted: (_) => _loading ? null : _submit(),
                        decoration: _campo(
                          '••••••••',
                          sufijo: IconButton(
                            icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined, size: 20, color: _gris),
                            onPressed: () => setState(() => _obscure = !_obscure),
                          ),
                        ),
                      ),
                      const SizedBox(height: 30),
                      SizedBox(
                        height: 52,
                        child: FilledButton(
                          onPressed: _loading ? null : _submit,
                          style: FilledButton.styleFrom(
                            backgroundColor: _tinta,
                            disabledBackgroundColor: _tinta.withValues(alpha: 0.5),
                            foregroundColor: Colors.white,
                            shape: const StadiumBorder(),
                            textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 1.2),
                          ),
                          child: Text(_loading ? 'INGRESANDO...' : 'INICIAR SESIÓN'),
                        ),
                      ),
                      const SizedBox(height: 20),
                      const Row(
                        children: [
                          Expanded(child: Divider(color: _linea)),
                          Padding(
                            padding: EdgeInsets.symmetric(horizontal: 14),
                            child: Text('O', style: TextStyle(fontSize: 11, color: Color(0xFFAAAAAA))),
                          ),
                          Expanded(child: Divider(color: _linea)),
                        ],
                      ),
                      const SizedBox(height: 20),
                      GoogleAuthButton(label: 'Continuar con Google', loading: _loadingGoogle, onPressed: _continuarConGoogle),
                      const SizedBox(height: 10),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Text('¿No tienes cuenta? ', style: TextStyle(color: Color(0xFF555555))),
                          GestureDetector(
                            onTap: _irARegistro,
                            child: const Text(
                              'Crea una aquí',
                              style: TextStyle(fontWeight: FontWeight.w700, color: _tinta, decoration: TextDecoration.underline),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 26),
                      const Divider(color: _linea),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          _ventaja('Tienda', 'ONLINE'),
                          _ventaja('Caja', 'SIN INTERNET'),
                          _ventaja('Probador', 'VIRTUAL'),
                        ],
                      ),
                    ],
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
