import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_config.dart';
import '../auth/auth_provider.dart';
import '../auth/perfil_personal.dart' show marcaPersonalProvider;
import '../portada/plataforma_data.dart' show colorMarca;
import 'admin_menu.dart';

const _fondo = Color(0xFFF7F5F3);
const _borde = Color(0xFFE6E1DC);
const _gris = Color(0xFF777777);

/// Panel de la tienda (`admin-layout` de la web, version responsive): barra
/// con el logo y el color de la tienda, los paquetes P1-P5 (al tocar uno se
/// despliegan sus CUs) y el inicio con los accesos rapidos segun el rol.
class AdminShell extends ConsumerStatefulWidget {
  const AdminShell({super.key});

  @override
  ConsumerState<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends ConsumerState<AdminShell> {
  String? _abierto;

  String _estado(AuthState auth, AdminUseCase uc) {
    if (uc.route == null) return 'proximamente';
    if (uc.code == 'CU15') return 'ok';
    return auth.isAdministrador || auth.hasPermiso(uc.permiso ?? uc.code) ? 'ok' : 'sin-acceso';
  }

  Future<void> _salir() async {
    await ref.read(authProvider.notifier).logout();
    if (mounted) context.go('/login');
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final usuario = auth.usuario;
    final marca = ref.watch(marcaPersonalProvider).valueOrNull;
    // El color de la tienda reemplaza al del panel (como --brand-dark en la web).
    final color = colorMarca(marca?['color_marca'] as String?);
    final nombre = marca?['nombre']?.toString() ?? '';
    final logo = marca?['logo_url'] as String?;
    final paquete = adminMenu.where((p) => p.code == _abierto).firstOrNull;
    final accesos = [
      for (final p in adminMenu)
        for (final uc in p.useCases)
          if (_estado(auth, uc) == 'ok') uc,
    ];

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: _fondo,
        body: ListView(padding: EdgeInsets.zero, children: [
          // Barra superior
          Container(
            color: color,
            padding: EdgeInsets.fromLTRB(16, MediaQuery.paddingOf(context).top + 10, 16, 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                if (logo != null)
                  Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(6)),
                    child: CachedNetworkImage(imageUrl: resolveImageUrl(logo), height: 34, fit: BoxFit.contain),
                  )
                else if (nombre.isNotEmpty) ...[
                  Container(
                    width: 34,
                    height: 34,
                    alignment: Alignment.center,
                    color: Colors.white,
                    child: Text(nombre[0].toUpperCase(), style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 18)),
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(nombre,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.inter(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 15)),
                  ),
                ],
                const Spacer(),
                OutlinedButton(
                  onPressed: _salir,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: BorderSide(color: Colors.white.withValues(alpha: 0.5)),
                    shape: const RoundedRectangleBorder(),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  ),
                  child: Text('CERRAR SESION', style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w800)),
                ),
              ]),
              const SizedBox(height: 10),
              Row(children: [
                Expanded(
                  child: Text('PANEL DE ADMINISTRACION · ${usuario?.nombre ?? ''}',
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.inter(color: Colors.white70, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.5)),
                ),
                if (auth.isAdministrador)
                  InkWell(
                    onTap: () => context.push('/admin/suscripcion'),
                    child: Text('MI SUSCRIPCIÓN',
                        style: GoogleFonts.inter(
                            color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800, decoration: TextDecoration.underline,
                            decorationColor: Colors.white)),
                  ),
              ]),
            ]),
          ),
          // Paquetes P1-P5
          Container(
            color: Colors.white,
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
            child: Column(children: [
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                for (final p in adminMenu)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: GestureDetector(
                      onTap: () => setState(() => _abierto = _abierto == p.code ? null : p.code),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        width: 58,
                        height: 58,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: _abierto == p.code ? color : _fondo,
                          border: Border.all(color: _abierto == p.code ? color : _borde),
                        ),
                        child: Text(p.code,
                            style: GoogleFonts.inter(
                                fontSize: 14, fontWeight: FontWeight.w900, color: _abierto == p.code ? Colors.white : color)),
                      ),
                    ),
                  ),
              ]),
              AnimatedSize(
                duration: const Duration(milliseconds: 220),
                curve: Curves.easeOut,
                child: paquete == null
                    ? const SizedBox(width: double.infinity)
                    : Container(
                        width: double.infinity,
                        margin: const EdgeInsets.only(top: 14),
                        decoration: BoxDecoration(border: Border.all(color: _borde)),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                          Container(
                            padding: const EdgeInsets.all(12),
                            color: _fondo,
                            child: Text('${paquete.code} · ${paquete.label}'.toUpperCase(),
                                style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w800, letterSpacing: 0.5, color: color)),
                          ),
                          for (final uc in paquete.useCases)
                            _ItemCu(uc: uc, estado: _estado(auth, uc), color: color, onTap: () {
                              setState(() => _abierto = null);
                              context.push(uc.route!);
                            }),
                        ]),
                      ),
              ),
            ]),
          ),
          // Inicio: saludo y accesos rapidos
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 24, 16, 32),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('PANEL DE ADMINISTRACION',
                  style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.2, color: _gris)),
              const SizedBox(height: 4),
              Text('Hola, ${usuario?.nombre.split(' ').first ?? ''}',
                  style: GoogleFonts.inter(fontSize: 28, fontWeight: FontWeight.w900, color: color)),
              const SizedBox(height: 6),
              Text.rich(TextSpan(children: [
                const TextSpan(text: 'Accesos rapidos segun tu rol '),
                TextSpan(text: usuario?.rol ?? '', style: const TextStyle(fontWeight: FontWeight.w800)),
                const TextSpan(text: '. Tambien podes navegar con los paquetes P1-P5 de arriba.'),
              ]), style: GoogleFonts.inter(fontSize: 13.5, height: 1.5, color: _gris)),
              const SizedBox(height: 18),
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
                childAspectRatio: 1.45,
                children: [
                  for (final uc in accesos)
                    Material(
                      color: Colors.white,
                      child: InkWell(
                        onTap: () => context.push(uc.route!),
                        child: Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(border: Border.all(color: _borde)),
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(uc.code, style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w900, color: color)),
                            const SizedBox(height: 6),
                            Expanded(
                              child: Text(uc.label,
                                  overflow: TextOverflow.fade,
                                  style: GoogleFonts.inter(fontSize: 13.5, fontWeight: FontWeight.w700, color: const Color(0xFF2B2B2B))),
                            ),
                          ]),
                        ),
                      ),
                    ),
                ],
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _ItemCu extends StatelessWidget {
  const _ItemCu({required this.uc, required this.estado, required this.color, required this.onTap});
  final AdminUseCase uc;
  final String estado;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ok = estado == 'ok';
    return InkWell(
      onTap: ok ? onTap : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        decoration: const BoxDecoration(border: Border(top: BorderSide(color: _borde))),
        child: Row(children: [
          SizedBox(
            width: 44,
            child: Text(uc.code, style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w900, color: ok ? color : _gris)),
          ),
          Expanded(
            child: Text(uc.label, style: GoogleFonts.inter(fontSize: 13.5, color: ok ? const Color(0xFF2B2B2B) : const Color(0xFFAAAAAA))),
          ),
          if (!ok)
            Text(estado == 'sin-acceso' ? 'Sin acceso' : 'Proximamente',
                style: GoogleFonts.inter(fontSize: 11, fontStyle: FontStyle.italic, color: const Color(0xFFAAAAAA))),
        ]),
      ),
    );
  }
}
