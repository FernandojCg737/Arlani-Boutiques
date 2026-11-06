import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_config.dart';
import '../auth/auth_provider.dart';
import 'super_bitacora.dart';
import 'super_live.dart';
import 'superadmin_menu.dart';

const noche = Color(0xFF121A2C);
const marfil = Color(0xFFF4F1EE);
const _beige = Color(0xFFEFEAE4);
const _borde = Color(0xFFE4DED7);
const _gris = Color(0xFF5F6779);
const _rojo = Color(0xFFE5674F);

/// Panel del SuperAdministrador en el celular: el mismo panel de la web en
/// version responsiva. Arriba el encabezado, el selector 1er/2do parcial y
/// los paquetes P1-P5 (al tocar uno se despliegan sus CUs); debajo, la ruta
/// (parcial / paquete / CU) y la pantalla del CU. Entra directo a la bitacora.
class SuperadminShell extends ConsumerStatefulWidget {
  const SuperadminShell({super.key});

  @override
  ConsumerState<SuperadminShell> createState() => _SuperadminShellState();
}

class _SuperadminShellState extends ConsumerState<SuperadminShell> {
  String _parcial = 'p2';
  String? _abierto;
  // El CU que se esta viendo (parcial + codigo): empieza en la bitacora.
  UbicacionCaso _actual = buscarCaso('p2', 'CU08')!;
  final _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  ParcialMenu get _parcialMenu => parcialesSuperadmin.firstWhere((p) => p.id == _parcial);

  void _abrirCaso(PaqueteMenu paquete, CasoMenu caso) {
    setState(() {
      _actual = UbicacionCaso(_parcialMenu, paquete, caso);
      _abierto = null;
    });
    _scroll.animateTo(0, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
  }

  void _irAlSegundo(String codigo) {
    final u = buscarCaso('p2', codigo);
    if (u == null) return;
    setState(() {
      _parcial = 'p2';
      _actual = u;
      _abierto = null;
    });
  }

  Future<void> _cerrarSesion() async {
    await ref.read(authProvider.notifier).logout();
    if (mounted) context.go('/login');
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: marfil,
        body: Column(children: [
          _barra(),
          Expanded(
            child: ListView(
              controller: _scroll,
              padding: EdgeInsets.only(bottom: 32 + MediaQuery.paddingOf(context).bottom),
              children: [
                _navegacion(),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 18, 16, 0),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    _contexto(),
                    const SizedBox(height: 26),
                    _pantalla(),
                  ]),
                ),
              ],
            ),
          ),
        ]),
      ),
    );
  }

  // ------------------------------------------------------------------ barra

  Widget _barra() => Container(
        color: noche,
        padding: EdgeInsets.fromLTRB(16, MediaQuery.paddingOf(context).top + 8, 16, 10),
        child: Row(children: [
          Image.asset('assets/portada/arlani-logo-encabezado.png', height: 40),
          const Spacer(),
          OutlinedButton(
            onPressed: _cerrarSesion,
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.white,
              side: BorderSide(color: Colors.white.withValues(alpha: 0.45)),
              shape: const StadiumBorder(),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            ),
            child: Text('CERRAR SESIÓN', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w800, letterSpacing: 0.3)),
          ),
        ]),
      );

  // ------------------------------------------------------------- navegacion

  Widget _navegacion() {
    final paquete = _parcialMenu.paquetes.where((p) => p.codigo == _abierto).firstOrNull;
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
      child: Column(children: [
        // 1er / 2do parcial
        Container(
          padding: const EdgeInsets.all(6),
          decoration: BoxDecoration(color: _beige, borderRadius: BorderRadius.circular(18)),
          child: Row(children: [
            for (final p in parcialesSuperadmin)
              Expanded(
                child: GestureDetector(
                  onTap: () => setState(() {
                    _parcial = p.id;
                    _abierto = null;
                  }),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    decoration: BoxDecoration(
                      color: _parcial == p.id ? noche : Colors.transparent,
                      borderRadius: BorderRadius.circular(13),
                      boxShadow: _parcial == p.id ? const [BoxShadow(color: Color(0x33121A2C), blurRadius: 10, offset: Offset(0, 4))] : null,
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      p.nombre.toUpperCase(),
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                        color: _parcial == p.id ? Colors.white : _gris,
                      ),
                    ),
                  ),
                ),
              ),
          ]),
        ),
        const SizedBox(height: 14),
        // P1 ... P5
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          for (final pk in _parcialMenu.paquetes)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: _Paquete(
                codigo: pk.codigo,
                abierto: _abierto == pk.codigo,
                actual: _actual.parcial.id == _parcial && _actual.paquete.codigo == pk.codigo,
                onTap: () => setState(() => _abierto = _abierto == pk.codigo ? null : pk.codigo),
              ),
            ),
        ]),
        AnimatedSize(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
          child: paquete == null ? const SizedBox(width: double.infinity) : _desplegable(paquete),
        ),
      ]),
    );
  }

  Widget _desplegable(PaqueteMenu pk) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 14),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: _borde), borderRadius: BorderRadius.circular(12)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _borde))),
          child: Text('${_parcialMenu.nombre} · ${pk.codigo} · ${pk.nombre}',
              style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w800, letterSpacing: 0.4, color: _gris)),
        ),
        if (pk.casos.isEmpty)
          Padding(
            padding: const EdgeInsets.all(14),
            child: Text('Todos los CUs de este paquete pasaron al 2do parcial.',
                style: GoogleFonts.inter(fontSize: 13, color: _gris)),
          ),
        for (final c in pk.casos)
          InkWell(
            onTap: () => _abrirCaso(pk, c),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              color: _actual.caso == c ? const Color(0xFFF7F4F2) : null,
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(
                  width: 46,
                  child: Text(c.codigo, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w900, color: noche)),
                ),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(c.nombre, style: GoogleFonts.inter(fontSize: 13.5, color: noche)),
                    if (c.antes != null || c.porEmpresa)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Wrap(spacing: 6, runSpacing: 4, children: [
                          if (c.antes != null) _Etiqueta('antes ${c.antes}'),
                          if (c.porEmpresa) const _Etiqueta('Por empresa', empresa: true),
                        ]),
                      ),
                  ]),
                ),
              ]),
            ),
          ),
        if (pk.movidos.isNotEmpty)
          Container(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
            decoration: const BoxDecoration(border: Border(top: BorderSide(color: _borde))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('PASARON AL 2DO PARCIAL',
                  style: GoogleFonts.inter(fontSize: 10.5, fontWeight: FontWeight.w800, letterSpacing: 0.6, color: _gris)),
              for (final m in pk.movidos)
                InkWell(
                  onTap: () => _irAlSegundo(m.a),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 7),
                    child: Text.rich(TextSpan(children: [
                      TextSpan(text: m.de, style: const TextStyle(decoration: TextDecoration.lineThrough, color: _gris)),
                      const TextSpan(text: '  →  '),
                      TextSpan(text: m.a, style: const TextStyle(fontWeight: FontWeight.w900)),
                      TextSpan(text: '  ${m.nombre}'),
                    ]), style: GoogleFonts.inter(fontSize: 13, color: noche)),
                  ),
                ),
            ]),
          ),
      ]),
    );
  }

  // --------------------------------------------------------------- contexto

  Widget _contexto() {
    final u = _actual;
    return Text.rich(
      TextSpan(children: [
        TextSpan(text: u.parcial.nombre.toUpperCase(), style: const TextStyle(fontWeight: FontWeight.w900)),
        const TextSpan(text: '  /  ', style: TextStyle(color: Color(0xFFB9B2AA))),
        TextSpan(text: '${u.paquete.codigo} · ${u.paquete.nombre}'),
        const TextSpan(text: '  /  ', style: TextStyle(color: Color(0xFFB9B2AA))),
        TextSpan(text: '${u.caso.codigo} ', style: const TextStyle(fontWeight: FontWeight.w900)),
        TextSpan(text: u.caso.nombre),
        if (u.caso.antes != null && u.parcial.id == 'p2')
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: Padding(padding: const EdgeInsets.only(left: 8), child: _Etiqueta('antes ${u.caso.antes} en el 1er parcial')),
          ),
      ]),
      style: GoogleFonts.inter(fontSize: 12.5, height: 1.6, color: noche),
    );
  }

  // ---------------------------------------------------------------- pantalla

  Widget _pantalla() {
    final caso = _actual.caso;
    final titulo = switch (caso.codigo) {
      'CU08' when _actual.parcial.id == 'p2' => 'Auditar operaciones',
      'CU22' => 'Live commerce',
      _ => caso.nombre,
    };
    final Widget contenido = switch ((_actual.parcial.id, caso.codigo)) {
      ('p2', 'CU08') => const SuperBitacora(),
      ('p2', 'CU22') => const SuperLive(),
      _ => _EnLaWeb(caso: caso),
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(titulo.toUpperCase(),
          style: GoogleFonts.inter(fontSize: 26, fontWeight: FontWeight.w900, height: 1.15, letterSpacing: -0.3, color: noche)),
      if (caso.descripcion != null) ...[
        const SizedBox(height: 10),
        Text(caso.descripcion!, style: GoogleFonts.inter(fontSize: 14.5, height: 1.5, color: _gris)),
      ],
      const SizedBox(height: 22),
      // Una pantalla por CU (al cambiar de CU se crea de nuevo).
      KeyedSubtree(key: ValueKey('${_actual.parcial.id}-${caso.codigo}'), child: contenido),
    ]);
  }
}

class _Paquete extends StatelessWidget {
  const _Paquete({required this.codigo, required this.abierto, required this.actual, required this.onTap});
  final String codigo;
  final bool abierto;
  final bool actual;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        width: 58,
        height: 58,
        decoration: BoxDecoration(
          color: abierto ? noche : const Color(0xFFF7F4F2),
          border: Border.all(color: abierto ? noche : _borde),
        ),
        child: Stack(alignment: Alignment.center, children: [
          Text(codigo, style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w900, color: abierto ? Colors.white : noche)),
          if (actual)
            Positioned(
              bottom: 9,
              child: Container(width: 6, height: 6, decoration: const BoxDecoration(color: _rojo, shape: BoxShape.circle)),
            ),
        ]),
      ),
    );
  }
}

class _Etiqueta extends StatelessWidget {
  const _Etiqueta(this.texto, {this.empresa = false});
  final String texto;
  final bool empresa;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: empresa ? const Color(0xFFE8F0FB) : const Color(0xFFF0ECE7),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(texto,
            style: GoogleFonts.inter(fontSize: 10.5, color: empresa ? const Color(0xFF1C5FA8) : _gris, fontStyle: FontStyle.italic)),
      );
}

/// CUs que todavia no tienen pantalla en el celular: se abren en la web.
class _EnLaWeb extends StatelessWidget {
  const _EnLaWeb({required this.caso});
  final CasoMenu caso;

  @override
  Widget build(BuildContext context) {
    final url = '$webAssetsBaseUrl/superadmin/${caso.ruta ?? ''}';
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: _borde)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Icon(Icons.desktop_windows_outlined, color: noche, size: 30),
        const SizedBox(height: 10),
        Text('Este CU se gestiona en el panel web',
            style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w800, color: noche)),
        const SizedBox(height: 6),
        Text(
          caso.porEmpresa
              ? 'Se trabaja dentro de una tienda (primero se elige la tienda). Ábrelo en la web para verlo completo.'
              : 'Ábrelo en la web para verlo completo; en el celular están la bitácora y el live commerce.',
          style: GoogleFonts.inter(fontSize: 13.5, height: 1.5, color: _gris),
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          style: FilledButton.styleFrom(backgroundColor: noche, shape: const RoundedRectangleBorder()),
          onPressed: () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
          icon: const Icon(Icons.open_in_new, size: 18),
          label: const Text('ABRIR EN LA WEB'),
        ),
      ]),
    );
  }
}
