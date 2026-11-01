import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../widgets/password_strength.dart';
import 'auth_provider.dart';

enum _Step { email, code, choice, reset }

class RecuperarPasswordScreen extends ConsumerStatefulWidget {
  const RecuperarPasswordScreen({super.key});

  @override
  ConsumerState<RecuperarPasswordScreen> createState() => _RecuperarPasswordScreenState();
}

class _RecuperarPasswordScreenState extends ConsumerState<RecuperarPasswordScreen> {
  _Step _step = _Step.email;
  final _emailCtrl = TextEditingController();
  final _codeCtrl = TextEditingController();
  final _newPasswordCtrl = TextEditingController();
  final _confirmCtrl = TextEditingController();
  String? _resetToken;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _codeCtrl.dispose();
    _newPasswordCtrl.dispose();
    _confirmCtrl.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await action();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _sendEmail() => _run(() async {
    if (_emailCtrl.text.trim().isEmpty) throw Exception('Ingresa tu correo.');
    await ref.read(authProvider.notifier).forgotPassword(_emailCtrl.text.trim());
    setState(() => _step = _Step.code);
  });

  Future<void> _verifyCode() => _run(() async {
    if (_codeCtrl.text.trim().length != 6) throw Exception('El codigo tiene 6 digitos.');
    final token = await ref
        .read(authProvider.notifier)
        .verifyResetCode(email: _emailCtrl.text.trim(), code: _codeCtrl.text.trim());
    _resetToken = token;
    setState(() => _step = _Step.choice);
  });

  Future<void> _loginDirecto() => _run(() async {
    await ref.read(authProvider.notifier).loginWithResetCode(_resetToken!);
    if (!mounted) return;
    final auth = ref.read(authProvider);
    context.go(auth.isStaff ? '/admin' : '/');
  });

  Future<void> _cambiarPassword() => _run(() async {
    if (!isPasswordValid(_newPasswordCtrl.text)) throw Exception('La contrasena no cumple los requisitos.');
    if (_newPasswordCtrl.text != _confirmCtrl.text) throw Exception('Las contrasenas no coinciden.');
    await ref.read(authProvider.notifier).resetPassword(resetToken: _resetToken!, newPassword: _newPasswordCtrl.text);
    if (!mounted) return;
    final auth = ref.read(authProvider);
    context.go(auth.isStaff ? '/admin' : '/');
  });

  // Mismo diseño que el login de Arlani (y que `recuperar-password` de la
  // web en celular): fondo claro con marca de agua, campos subrayados y
  // botones redondeados en el azul oscuro del SaaS.
  static const _tinta = Color(0xFF121A2C);
  static const _gris = Color(0xFF6B6B6B);
  static const _linea = Color(0xFFE2E2E2);
  static const _etiqueta = TextStyle(fontSize: 11, letterSpacing: 1.4, fontWeight: FontWeight.w700, color: _gris);

  InputDecoration _campo(String pista) => InputDecoration(
        hintText: pista,
        hintStyle: const TextStyle(color: Color(0xFFAAAAAA), fontSize: 15),
        filled: false,
        isDense: true,
        counterText: '',
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        border: const UnderlineInputBorder(borderSide: BorderSide(color: _linea)),
        enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: _linea)),
        focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: _tinta, width: 1.4)),
      );

  Widget _principal(String texto, VoidCallback onPressed) => SizedBox(
        height: 52,
        child: FilledButton(
          onPressed: _loading ? null : onPressed,
          style: FilledButton.styleFrom(
            backgroundColor: _tinta,
            disabledBackgroundColor: _tinta.withValues(alpha: 0.5),
            foregroundColor: Colors.white,
            shape: const StadiumBorder(),
            textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, letterSpacing: 1.2),
          ),
          child: Text(texto),
        ),
      );

  Widget _secundario(String texto, VoidCallback onPressed) => SizedBox(
        height: 50,
        child: OutlinedButton(
          onPressed: _loading ? null : onPressed,
          style: OutlinedButton.styleFrom(
            foregroundColor: _tinta,
            side: const BorderSide(color: _linea),
            shape: const RoundedRectangleBorder(),
            textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 1.2),
          ),
          child: Text(texto),
        ),
      );

  Widget _titulo(String titulo, Widget texto) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w500, color: _tinta, height: 1.2)),
          const SizedBox(height: 12),
          DefaultTextStyle.merge(style: const TextStyle(fontSize: 15, height: 1.5, color: Color(0xFF555555)), child: texto),
          const SizedBox(height: 26),
        ],
      );

  @override
  Widget build(BuildContext context) {
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
                          onPressed: () => context.go('/'),
                          style: TextButton.styleFrom(foregroundColor: _gris, padding: EdgeInsets.zero),
                          icon: const Icon(Icons.arrow_back, size: 16),
                          label: const Text('VOLVER AL INICIO', style: _etiqueta),
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
                          Text('RECUPERAR ACCESO', style: _etiqueta),
                        ],
                      ),
                      const SizedBox(height: 12),
                      if (_error != null)
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(12),
                          margin: const EdgeInsets.only(bottom: 16),
                          color: const Color(0xFFFDECEA),
                          child: Text(_error!, style: const TextStyle(color: Color(0xFFB3261E), fontSize: 13)),
                        ),
                      ..._buildStep(),
                      const SizedBox(height: 10),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Text('¿Ya te acordaste? ', style: TextStyle(color: Color(0xFF555555))),
                          GestureDetector(
                            onTap: () => context.canPop() ? context.pop() : context.go('/login'),
                            child: const Text(
                              'Inicia sesión aquí',
                              style: TextStyle(fontWeight: FontWeight.w700, color: _tinta, decoration: TextDecoration.underline),
                            ),
                          ),
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

  List<Widget> _buildStep() {
    switch (_step) {
      case _Step.email:
        return [
          _titulo('¿OLVIDASTE TU CONTRASEÑA?',
              const Text('Ingresa el correo con el que te registraste y te enviaremos un código de verificación.')),
          const Text('CORREO ELECTRÓNICO', style: _etiqueta),
          TextField(
            controller: _emailCtrl,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            onSubmitted: (_) => _loading ? null : _sendEmail(),
            decoration: _campo('Introduce tu email'),
          ),
          const SizedBox(height: 30),
          _principal(_loading ? 'ENVIANDO...' : 'ENVIAR CÓDIGO', _sendEmail),
        ];
      case _Step.code:
        return [
          _titulo(
            'REVISA TU CORREO',
            Text.rich(TextSpan(children: [
              const TextSpan(text: 'Te enviamos un código de 6 dígitos a '),
              TextSpan(text: _emailCtrl.text.trim(), style: const TextStyle(fontWeight: FontWeight.w700, color: _tinta)),
              const TextSpan(text: '. Ingrésalo para continuar.'),
            ])),
          ),
          const Text('CÓDIGO DE VERIFICACIÓN', style: _etiqueta),
          TextField(
            controller: _codeCtrl,
            keyboardType: TextInputType.number,
            maxLength: 6,
            onSubmitted: (_) => _loading ? null : _verifyCode(),
            decoration: _campo('000000'),
          ),
          const SizedBox(height: 30),
          _principal(_loading ? 'VERIFICANDO...' : 'VERIFICAR CÓDIGO', _verifyCode),
        ];
      case _Step.choice:
        return [
          _titulo('IDENTIDAD VERIFICADA', const Text('Confirmamos que esta cuenta te pertenece. ¿Qué quieres hacer?')),
          _principal('CAMBIAR CONTRASEÑA', () => setState(() => _step = _Step.reset)),
          const SizedBox(height: 12),
          _secundario(_loading ? 'INGRESANDO...' : 'CONTINUAR A LA SESIÓN', _loginDirecto),
        ];
      case _Step.reset:
        return [
          _titulo('CREAR NUEVA CONTRASEÑA', const Text('Elige una contraseña nueva para tu cuenta.')),
          const Text('NUEVA CONTRASEÑA', style: _etiqueta),
          TextField(
            controller: _newPasswordCtrl,
            obscureText: true,
            onChanged: (_) => setState(() {}),
            decoration: _campo('••••••••'),
          ),
          const SizedBox(height: 10),
          PasswordStrengthChecklist(password: _newPasswordCtrl.text),
          const SizedBox(height: 22),
          const Text('CONFIRMAR CONTRASEÑA', style: _etiqueta),
          TextField(controller: _confirmCtrl, obscureText: true, decoration: _campo('••••••••')),
          const SizedBox(height: 30),
          _principal(_loading ? 'GUARDANDO...' : 'GUARDAR NUEVA CONTRASEÑA', _cambiarPassword),
        ];
    }
  }
}
