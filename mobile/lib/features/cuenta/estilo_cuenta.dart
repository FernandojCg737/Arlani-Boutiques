import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Colores de "Mi cuenta" en la web (perfil.scss).
const tintaCuenta = Color(0xFF121A2C);
const grisCuenta = Color(0xFF999999);
const grisOscuroCuenta = Color(0xFF666666);
const bordeCuenta = Color(0xFFEEEEEE);
const rojoCuenta = Color(0xFFB3261E);
const verdeCuenta = Color(0xFF2E7D32);
const ambarCuenta = Color(0xFFB26A00);

/// `.dash-card`: tarjeta blanca con borde fino.
class TarjetaCuenta extends StatelessWidget {
  const TarjetaCuenta({super.key, required this.child, this.padding = const EdgeInsets.all(18), this.destacada = false});

  final Widget child;
  final EdgeInsets padding;
  final bool destacada;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: destacada ? tintaCuenta : bordeCuenta, width: destacada ? 1.5 : 1),
      ),
      child: child,
    );
  }
}

/// Insignia de estado (`.admin-badge`): texto en mayuscula sobre su color.
class InsigniaEstado extends StatelessWidget {
  const InsigniaEstado({super.key, required this.texto, required this.tono});

  final String texto;
  final TonoEstado tono;

  @override
  Widget build(BuildContext context) {
    final (fg, bg) = switch (tono) {
      TonoEstado.ok => (verdeCuenta, const Color(0xFFEAF6EC)),
      TonoEstado.espera => (ambarCuenta, const Color(0xFFFFF4E0)),
      TonoEstado.mal => (rojoCuenta, const Color(0xFFFDECEA)),
      TonoEstado.neutro => (grisOscuroCuenta, const Color(0xFFF0F0F0)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      color: bg,
      child: Text(texto.toUpperCase(), style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.3, color: fg)),
    );
  }
}

enum TonoEstado { ok, espera, mal, neutro }

/// `.perfil-alert`
class AvisoCuenta extends StatelessWidget {
  const AvisoCuenta(this.texto, {super.key, this.error = false});

  final String texto;
  final bool error;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      color: error ? const Color(0xFFFDECEA) : const Color(0xFFEAF6EC),
      child: Text(texto, style: GoogleFonts.inter(fontSize: 13, color: error ? rojoCuenta : verdeCuenta)),
    );
  }
}

/// Texto gris de "todavia no hay..." (`.dash-vacio`).
Widget vacioCuenta(String texto) => Text(texto, style: GoogleFonts.inter(fontSize: 13, height: 1.5, color: grisCuenta));

Widget cargandoCuenta() => const Padding(padding: EdgeInsets.symmetric(vertical: 40), child: Center(child: CircularProgressIndicator()));

/// Enlace de texto subrayado (acciones de las tarjetas).
class EnlaceCuenta extends StatelessWidget {
  const EnlaceCuenta(this.texto, {super.key, required this.onTap, this.peligro = false});

  final String texto;
  final VoidCallback? onTap;
  final bool peligro;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Text(
          texto,
          style: GoogleFonts.inter(
            fontSize: 12.5,
            fontWeight: FontWeight.w700,
            color: peligro ? rojoCuenta : tintaCuenta,
            decoration: TextDecoration.underline,
            decorationColor: peligro ? rojoCuenta : tintaCuenta,
          ),
        ),
      ),
    );
  }
}

/// Boton lleno azul noche (`.perfil-btn-confirmar`) o con borde (`.perfil-btn-cancelar`).
class BotonCuenta extends StatelessWidget {
  const BotonCuenta(this.texto, {super.key, required this.onTap, this.lleno = true, this.ancho = false});

  final String texto;
  final VoidCallback? onTap;
  final bool lleno;
  final bool ancho;

  @override
  Widget build(BuildContext context) {
    final estilo = GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5);
    final forma = const RoundedRectangleBorder();
    final tam = ancho ? const Size.fromHeight(46) : const Size(0, 44);
    return lleno
        ? FilledButton(
            onPressed: onTap,
            style: FilledButton.styleFrom(
              backgroundColor: tintaCuenta,
              foregroundColor: Colors.white,
              disabledBackgroundColor: tintaCuenta.withValues(alpha: 0.5),
              disabledForegroundColor: Colors.white,
              shape: forma,
              minimumSize: tam,
              padding: const EdgeInsets.symmetric(horizontal: 18),
              textStyle: estilo,
            ),
            child: Text(texto.toUpperCase()),
          )
        : OutlinedButton(
            onPressed: onTap,
            style: OutlinedButton.styleFrom(
              foregroundColor: tintaCuenta,
              side: const BorderSide(color: Color(0xFFDDDDDD)),
              shape: forma,
              minimumSize: tam,
              padding: const EdgeInsets.symmetric(horizontal: 18),
              textStyle: estilo,
            ),
            child: Text(texto.toUpperCase()),
          );
  }
}

/// Confirmacion simple (el `confirm()` de la web).
Future<bool> confirmarCuenta(BuildContext context, String mensaje, {String si = 'Sí'}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      shape: const RoundedRectangleBorder(),
      content: Text(mensaje, style: GoogleFonts.inter(fontSize: 14.5, height: 1.45, color: tintaCuenta)),
      actions: [
        TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: Text('No', style: GoogleFonts.inter(color: grisOscuroCuenta))),
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(true),
          child: Text(si, style: GoogleFonts.inter(fontWeight: FontWeight.w700, color: tintaCuenta)),
        ),
      ],
    ),
  );
  return r ?? false;
}

/// Etiqueta de campo de formulario (`.devolucion-campo label`).
Widget etiquetaCampo(String texto) => Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(texto.toUpperCase(),
          style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: grisCuenta)),
    );

InputDecoration decoracionCampo({String? pista}) => InputDecoration(
      hintText: pista,
      hintStyle: GoogleFonts.inter(fontSize: 14, color: const Color(0xFFBBBBBB)),
      isDense: true,
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      border: const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: Color(0xFFDDDDDD))),
      enabledBorder: const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: Color(0xFFDDDDDD))),
      focusedBorder: const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: tintaCuenta)),
    );

/// Hoja inferior de pantalla completa para los formularios (`.perfil-modal`).
Future<T?> abrirHojaCuenta<T>(BuildContext context, {required String titulo, String? subtitulo, required Widget Function(BuildContext) cuerpo}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(),
    builder: (ctx) => Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(ctx).bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(20, 18, 8, 14),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: bordeCuenta))),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(titulo, style: GoogleFonts.inter(fontSize: 17, fontWeight: FontWeight.w800, color: tintaCuenta)),
                      if (subtitulo != null) ...[
                        const SizedBox(height: 4),
                        Text(subtitulo, style: GoogleFonts.inter(fontSize: 12.5, color: grisOscuroCuenta)),
                      ],
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Cerrar',
                  icon: const Icon(Icons.close, color: tintaCuenta),
                  onPressed: () => Navigator.of(ctx).pop(),
                ),
              ],
            ),
          ),
          Flexible(child: cuerpo(ctx)),
        ],
      ),
    ),
  );
}
