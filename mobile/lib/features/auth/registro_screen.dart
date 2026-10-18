import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../widgets/password_strength.dart';
import 'auth_provider.dart';
import 'google_auth.dart';
import 'google_auth_button.dart';

class RegistroScreen extends ConsumerStatefulWidget {
  const RegistroScreen({super.key, this.onSuccess, this.onIrALogin});

  /// Igual que en LoginScreen: si se abrio empujada desde una accion que
  /// necesitaba sesion (carrito, reservar, probador AR), al registrarse
  /// vuelve y retoma esa accion en vez de ir al inicio.
  final VoidCallback? onSuccess;

  /// "Ya tenes cuenta? Inicia sesion" cuando esta pantalla se abrio fuera
  /// del router (ver `asegurarSesion`); por defecto hace pop.
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
  bool _loading = false;
  bool _loadingGoogle = false;
  String? _error;

  @override
  void dispose() {
    _nombreCtrl.dispose();
    _emailCtrl.dispose();
    _telefonoCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_nombreCtrl.text.trim().isEmpty || _emailCtrl.text.trim().isEmpty) {
      setState(() => _error = 'Completa nombre y correo.');
      return;
    }
    if (!isPasswordValid(_passwordCtrl.text)) {
      setState(() => _error = 'La contrasena no cumple los requisitos.');
      return;
    }
    if (_passwordCtrl.text != _confirmCtrl.text) {
      setState(() => _error = 'Las contrasenas no coinciden.');
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('CREAR CUENTA')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error != null)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 16),
                  color: AppColors.dangerBg,
                  child: Text(_error!, style: const TextStyle(color: AppColors.danger, fontSize: 13)),
                ),
              TextField(controller: _nombreCtrl, decoration: const InputDecoration(labelText: 'NOMBRE COMPLETO')),
              const SizedBox(height: 18),
              TextField(
                controller: _emailCtrl,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'CORREO ELECTRONICO'),
              ),
              const SizedBox(height: 18),
              TextField(
                controller: _telefonoCtrl,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: 'TELEFONO (OPCIONAL)'),
              ),
              const SizedBox(height: 18),
              TextField(
                controller: _passwordCtrl,
                obscureText: true,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(labelText: 'CONTRASENA'),
              ),
              const SizedBox(height: 10),
              PasswordStrengthChecklist(password: _passwordCtrl.text),
              const SizedBox(height: 18),
              TextField(
                controller: _confirmCtrl,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'CONFIRMAR CONTRASENA'),
              ),
              const SizedBox(height: 28),
              ElevatedButton(
                onPressed: _loading ? null : _submit,
                child: Text(_loading ? 'CREANDO...' : 'CREAR CUENTA'),
              ),
              const OrDivider(),
              GoogleAuthButton(label: 'REGISTRARSE CON GOOGLE', loading: _loadingGoogle, onPressed: _registrarseConGoogle),
              const SizedBox(height: 16),
              Center(
                child: TextButton(
                  onPressed: widget.onIrALogin ?? () => context.pop(),
                  child: const Text('Ya tenes cuenta? Inicia sesion'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
