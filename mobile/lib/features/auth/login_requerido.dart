import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import 'auth_provider.dart';
import 'login_screen.dart';
import 'registro_screen.dart';

/// Equivalente al modal `LoginRequerido` de la web: carrito, reservar y el
/// probador AR se muestran tambien sin sesion, pero al usarlos se avisa que
/// hace falta iniciar sesion (o crear una cuenta) en vez de ocultarlos.
///
/// Devuelve `true` si al terminar hay sesion iniciada (ya la habia, o el
/// usuario se logueo/registro), asi el llamador retoma la accion:
///
///   if (!await asegurarSesion(context, ref, accion: 'para reservar')) return;
Future<bool> asegurarSesion(BuildContext context, WidgetRef ref, {required String accion}) async {
  if (ref.read(authProvider).isAuthenticated) return true;

  final opcion = await showModalBottomSheet<String>(
    context: context,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(),
    builder: (ctx) => _AvisoLoginRequerido(accion: accion),
  );
  if (opcion == null || !context.mounted) return false;

  // Pantalla completa (navegador raiz): tapa tambien la barra inferior.
  final navigator = Navigator.of(context, rootNavigator: true);
  void volver() => navigator.pop();

  await navigator.push(
    MaterialPageRoute(
      builder: (_) => opcion == 'registro'
          ? RegistroScreen(
              onSuccess: volver,
              // Desde el registro, "ya tengo cuenta" cambia a login sin
              // perder la accion pendiente.
              onIrALogin: () => navigator.pushReplacement(
                MaterialPageRoute(builder: (_) => LoginScreen(onSuccess: volver)),
              ),
            )
          : LoginScreen(onSuccess: volver),
    ),
  );
  return context.mounted && ref.read(authProvider).isAuthenticated;
}

class _AvisoLoginRequerido extends StatelessWidget {
  const _AvisoLoginRequerido({required this.accion});

  final String accion;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 28, 24, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(Icons.lock_outline, size: 36, color: AppColors.brandDark),
            const SizedBox(height: 12),
            const Text(
              'INICIA SESION',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.brandDark),
            ),
            const SizedBox(height: 8),
            Text(
              'Necesitas iniciar sesion $accion.',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 14, height: 1.4, color: AppColors.grayTextDark),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () => Navigator.of(context).pop('login'),
              child: const Text('INICIAR SESION'),
            ),
            const SizedBox(height: 10),
            OutlinedButton(
              onPressed: () => Navigator.of(context).pop('registro'),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(48),
                foregroundColor: AppColors.brandDark,
                side: const BorderSide(color: AppColors.brandDark),
                shape: const RoundedRectangleBorder(),
              ),
              child: const Text('CREAR UNA CUENTA'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Ahora no', style: TextStyle(color: AppColors.grayText)),
            ),
          ],
        ),
      ),
    );
  }
}
