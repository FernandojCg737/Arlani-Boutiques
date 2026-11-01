import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../auth/auth_provider.dart';
import 'admin_menu.dart';

/// Pantalla `/admin`: lista de paquetes (P1-P5) con sus CUs, igual que el
/// sidebar `admin-layout.ts` de la web. Cada CU se marca ok/sin-acceso segun
/// `hasPermiso` (bypaseado por completo si `isAdministrador`), y sin-ruta
/// (CU09-11,13-16,18,20,21) se muestra deshabilitado como "Proximamente".
class AdminShell extends ConsumerWidget {
  const AdminShell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final usuario = auth.usuario;

    return Scaffold(
      appBar: AppBar(
        title: const Text('PANEL ADMINISTRATIVO'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Cerrar sesion',
            onPressed: () async {
              await ref.read(authProvider.notifier).logout();
              if (context.mounted) context.go('/');
            },
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          Text('Hola, ${usuario?.nombre ?? ''}', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: AppColors.brandDark)),
          const SizedBox(height: 4),
          Text(
            usuario?.rol ?? usuario?.tipo ?? '',
            style: const TextStyle(color: AppColors.grayTextDark, fontSize: 13),
          ),
          const SizedBox(height: 24),
          for (final paquete in adminMenu) _PackageSection(paquete: paquete, auth: auth),
        ],
      ),
    );
  }
}

class _PackageSection extends StatelessWidget {
  const _PackageSection({required this.paquete, required this.auth});

  final AdminPackage paquete;
  final AuthState auth;

  @override
  Widget build(BuildContext context) {
    final visibles = paquete.useCases.where((cu) => cu.route != null).toList();
    if (visibles.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${paquete.code} · ${paquete.label}'.toUpperCase(),
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.grayText, letterSpacing: 0.6),
          ),
          const SizedBox(height: 8),
          Container(
            decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
            child: Column(
              children: [
                for (var i = 0; i < visibles.length; i++) ...[
                  if (i > 0) const Divider(height: 1),
                  _UseCaseTile(cu: visibles[i], auth: auth),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _UseCaseTile extends StatelessWidget {
  const _UseCaseTile({required this.cu, required this.auth});

  final AdminUseCase cu;
  final AuthState auth;

  @override
  Widget build(BuildContext context) {
    final permitido = auth.isAdministrador || auth.hasPermiso(cu.permiso ?? cu.code);

    return ListTile(
      dense: true,
      enabled: permitido,
      leading: Icon(
        permitido ? Icons.chevron_right : Icons.lock_outline,
        color: permitido ? AppColors.brandDark : AppColors.grayText,
        size: 20,
      ),
      title: Text(
        cu.label,
        style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: permitido ? AppColors.brandCharcoal : AppColors.grayText),
      ),
      subtitle: Text(cu.code, style: const TextStyle(fontSize: 11, color: AppColors.grayText)),
      onTap: permitido ? () => context.push(cu.route!) : null,
    );
  }
}
