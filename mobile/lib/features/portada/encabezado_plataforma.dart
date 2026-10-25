import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../auth/auth_provider.dart';
import '../storefront/cart_provider.dart';
import 'estilo_plataforma.dart';
import 'plataforma_data.dart';

/// Encabezado de la portada (`header-plataforma` de la web, version celular):
/// logo, carrito y hamburguesa. Va transparente sobre el video del hero y
/// pasa a "vidrio" (azul noche translucido y desenfocado) al bajar o al abrir
/// el menu.
class EncabezadoPlataforma extends ConsumerStatefulWidget {
  const EncabezadoPlataforma({super.key, required this.solido, required this.onIrA, required this.onBuscar});

  final bool solido;
  final void Function(SeccionPortada seccion) onIrA;
  final void Function(String texto) onBuscar;

  static const alto = 72.0;

  @override
  ConsumerState<EncabezadoPlataforma> createState() => _EncabezadoPlataformaState();
}

class _EncabezadoPlataformaState extends ConsumerState<EncabezadoPlataforma> {
  bool _menuAbierto = false;
  final _busqueda = TextEditingController();

  @override
  void dispose() {
    _busqueda.dispose();
    super.dispose();
  }

  void _cerrar() => setState(() => _menuAbierto = false);

  void _ir(SeccionPortada seccion) {
    _cerrar();
    widget.onIrA(seccion);
  }

  // Catalogo y carrito viven en el shell con barra inferior: se va (go); el
  // resto se apila sobre la portada (push) para volver con atras.
  void _navegar(String ruta) {
    _cerrar();
    if (ruta == '/catalogo' || ruta == '/carrito') {
      context.go(ruta);
    } else {
      context.push(ruta);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final enCarrito = ref.watch(cartTotalItemsProvider);
    final arriba = MediaQuery.paddingOf(context).top;
    final vidrio = widget.solido || _menuAbierto;

    final contenido = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(height: arriba),
        SizedBox(
          height: EncabezadoPlataforma.alto,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: Plataforma.margen),
            child: Row(
              children: [
                GestureDetector(
                  onTap: () {
                    _cerrar();
                    widget.onIrA(SeccionPortada.inicio);
                  },
                  child: Image.asset('assets/portada/arlani-logo-encabezado.png', height: 46),
                ),
                const Spacer(),
                if (auth.mostrarAccionCliente('CU13') && !auth.isStaff)
                  _BotonIcono(
                    icono: Icons.shopping_cart_outlined,
                    globo: enCarrito,
                    descripcion: 'Carrito',
                    onTap: () => _navegar('/carrito'),
                  ),
                const SizedBox(width: 4),
                _BotonIcono(
                  icono: _menuAbierto ? Icons.close : Icons.menu,
                  descripcion: _menuAbierto ? 'Cerrar menú' : 'Abrir menú',
                  onTap: () => setState(() => _menuAbierto = !_menuAbierto),
                ),
              ],
            ),
          ),
        ),
        if (_menuAbierto)
          ConstrainedBox(
            constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height - arriba - EncabezadoPlataforma.alto),
            child: _MenuMovil(
              busqueda: _busqueda,
              onBuscar: (texto) {
                _cerrar();
                widget.onBuscar(texto);
              },
              onIrA: _ir,
              onNavegar: _navegar,
              onCerrarSesion: () async {
                _cerrar();
                await ref.read(authProvider.notifier).logout();
              },
            ),
          ),
      ],
    );

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      curve: const Cubic(0.16, 1, 0.3, 1),
      color: vidrio ? Plataforma.vidrio : Colors.transparent,
      child: vidrio
          ? ClipRect(
              child: BackdropFilter(filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14), child: contenido),
            )
          : contenido,
    );
  }
}

class _BotonIcono extends StatelessWidget {
  const _BotonIcono({required this.icono, required this.descripcion, required this.onTap, this.globo = 0});

  final IconData icono;
  final String descripcion;
  final VoidCallback onTap;
  final int globo;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onTap,
      tooltip: descripcion,
      icon: Badge(
        isLabelVisible: globo > 0,
        backgroundColor: const Color(0xFFD32F2F),
        label: Text('$globo'),
        child: Icon(icono, color: Colors.white, size: 28),
      ),
    );
  }
}

/// `.movil` del encabezado web: buscador, los dos desplegables como acordeon
/// (+ / –), Precios, Catalogo y la cuenta.
class _MenuMovil extends ConsumerWidget {
  const _MenuMovil({
    required this.busqueda,
    required this.onBuscar,
    required this.onIrA,
    required this.onNavegar,
    required this.onCerrarSesion,
  });

  final TextEditingController busqueda;
  final void Function(String) onBuscar;
  final void Function(SeccionPortada) onIrA;
  final void Function(String) onNavegar;
  final VoidCallback onCerrarSesion;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final linea = BorderSide(color: Colors.white.withValues(alpha: 0.1));

    return Container(
      decoration: BoxDecoration(border: Border(top: linea)),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Plataforma.margen, 8, Plataforma.margen, 28),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              margin: const EdgeInsets.only(top: 8, bottom: 4),
              padding: const EdgeInsets.symmetric(horizontal: 14),
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(10)),
              child: Row(
                children: [
                  const Icon(Icons.search, color: Colors.white, size: 20),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: busqueda,
                      style: GoogleFonts.inter(color: Colors.white, fontSize: 16),
                      cursorColor: Plataforma.oro,
                      textInputAction: TextInputAction.search,
                      onSubmitted: onBuscar,
                      decoration: InputDecoration(
                        hintText: 'Buscar productos...',
                        hintStyle: GoogleFonts.inter(color: Colors.white.withValues(alpha: 0.65), fontSize: 16),
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            _Acordeon(titulo: 'Por qué Arlani', items: menuPorQue, onIrA: onIrA),
            _Acordeon(titulo: 'Funciones', items: menuFunciones, onIrA: onIrA),
            _EnlaceMenu(texto: 'Precios', onTap: () => onIrA(SeccionPortada.precios), borde: true),
            _EnlaceMenu(texto: 'Catálogo', onTap: () => onNavegar('/catalogo'), borde: true),
            const SizedBox(height: 8),
            if (auth.usuario != null) ...[
              if (auth.isStaff) _EnlaceMenu(texto: 'Mi panel', onTap: () => onNavegar('/admin')),
              _EnlaceMenu(texto: 'Mi perfil', onTap: () => onNavegar('/perfil')),
              _EnlaceMenu(texto: 'Cerrar sesión', onTap: onCerrarSesion),
            ] else ...[
              _EnlaceMenu(texto: 'Iniciar sesión', onTap: () => onNavegar('/login')),
              _EnlaceMenu(texto: 'Crear una cuenta', onTap: () => onNavegar('/registro')),
            ],
          ],
        ),
      ),
    );
  }
}

TextStyle _estiloMenu() => GoogleFonts.inter(
      color: Colors.white,
      fontSize: 15.2,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.9,
    );

class _EnlaceMenu extends StatelessWidget {
  const _EnlaceMenu({required this.texto, required this.onTap, this.borde = false});

  final String texto;
  final VoidCallback onTap;
  final bool borde;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(vertical: borde ? 16 : 12),
        decoration: borde
            ? BoxDecoration(border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.1))))
            : null,
        child: Text(texto.toUpperCase(), style: _estiloMenu()),
      ),
    );
  }
}

class _Acordeon extends StatefulWidget {
  const _Acordeon({required this.titulo, required this.items, required this.onIrA});

  final String titulo;
  final List<ItemMenuPlataforma> items;
  final void Function(SeccionPortada) onIrA;

  @override
  State<_Acordeon> createState() => _AcordeonState();
}

class _AcordeonState extends State<_Acordeon> {
  bool _abierto = false;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.1)))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => setState(() => _abierto = !_abierto),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Row(
                children: [
                  Expanded(child: Text(widget.titulo.toUpperCase(), style: _estiloMenu())),
                  Text(_abierto ? '–' : '+', style: _estiloMenu().copyWith(color: Plataforma.oro, fontSize: 18)),
                ],
              ),
            ),
          ),
          if (_abierto)
            for (final item in widget.items)
              InkWell(
                onTap: () => widget.onIrA(item.seccion),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 10, 0, 10),
                  child: Text(
                    item.titulo,
                    style: GoogleFonts.inter(color: Colors.white.withValues(alpha: 0.85), fontSize: 15),
                  ),
                ),
              ),
          if (_abierto) const SizedBox(height: 6),
        ],
      ),
    );
  }
}
