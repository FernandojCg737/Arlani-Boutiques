import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme.dart';
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(child: Image.asset('assets/logo.png', height: 72)),
                const SizedBox(height: 32),
                const EyebrowText('Bienvenido de nuevo'),
                const SizedBox(height: 8),
                const Text(
                  'INICIAR SESION',
                  style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: AppColors.brandDark),
                ),
                const SizedBox(height: 28),
                if (_error != null)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    margin: const EdgeInsets.only(bottom: 16),
                    color: AppColors.dangerBg,
                    child: Text(_error!, style: const TextStyle(color: AppColors.danger, fontSize: 13)),
                  ),
                TextField(
                  controller: _emailCtrl,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'CORREO ELECTRONICO'),
                ),
                const SizedBox(height: 20),
                TextField(
                  controller: _passwordCtrl,
                  obscureText: _obscure,
                  decoration: InputDecoration(
                    labelText: 'CONTRASENA',
                    suffixIcon: IconButton(
                      icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility, size: 20),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => context.push('/recuperar'),
                    child: const Text('Olvidaste tu contrasena?'),
                  ),
                ),
                const SizedBox(height: 12),
                ElevatedButton(
                  onPressed: _loading ? null : _submit,
                  child: Text(_loading ? 'INGRESANDO...' : 'INICIAR SESION'),
                ),
                const OrDivider(),
                GoogleAuthButton(label: 'CONTINUAR CON GOOGLE', loading: _loadingGoogle, onPressed: _continuarConGoogle),
                const SizedBox(height: 24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text('No tenes cuenta?', style: TextStyle(color: AppColors.grayTextDark)),
                    TextButton(onPressed: _irARegistro, child: const Text('Crear una cuenta')),
                  ],
                ),
                TextButton(
                  // Abierta desde una accion (onSuccess): "volver" regresa a
                  // donde estaba el cliente, no al inicio.
                  onPressed: widget.onSuccess != null ? () => Navigator.of(context).pop() : () => context.go('/'),
                  child: Text(
                    widget.onSuccess != null ? 'Volver' : 'Volver al inicio',
                    style: const TextStyle(color: AppColors.grayText),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
