import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Colores de la portada de Arlani Boutiques (la plataforma SaaS): los mismos
/// de las variables CSS de cada seccion en la web (`--noche`, `--marfil`,
/// `--coral`...), sacados del logo.
class Plataforma {
  Plataforma._();

  static const noche = Color(0xFF121A2C);
  static const fondo = Color(0xFF0B111D);
  static const lienzo = Color(0xFF0E1524);
  static const tarjeta = Color(0xFF121A2C);
  static const marfil = Color(0xFFF7F4F2);
  static const coral = Color(0xFFE8806B);
  static const coralOscuro = Color(0xFFC4503D);
  static const oro = Color(0xFFF2B8A6);
  static const gris = Color(0xFF5F6779);
  static const tinta = Color(0xFF1E2433);
  static const azulNoche = Color(0xFF1F2A44);

  /// Vidrio del encabezado al bajar: rgba(18, 26, 44, 0.6) con desenfoque.
  static const vidrio = Color(0x99121A2C);

  /// Degradado de los botones del plan recomendado y de la insignia.
  static const degradadoCoral = LinearGradient(colors: [coralOscuro, coral]);

  /// Margen lateral de las secciones en celular (clamp(20px, 6vw, 120px)).
  static const margen = 20.0;
}

/// Titulos grandes de la portada: Inter 800, italica, mayuscula, apretada.
TextStyle tituloPlataforma({double size = 34, Color color = Colors.white}) => GoogleFonts.inter(
      fontSize: size,
      fontWeight: FontWeight.w800,
      fontStyle: FontStyle.italic,
      height: 1.05,
      letterSpacing: -0.02 * size,
      color: color,
    );

/// Antetitulo chico en mayuscula ("PROMOCIONES", "PRECIOS"...).
TextStyle antetituloPlataforma(Color color) => GoogleFonts.inter(
      fontSize: 12.8,
      fontWeight: FontWeight.w700,
      letterSpacing: 1.0,
      color: color,
    );

/// Bricolage Grotesque: la tipografia de los numeros grandes y de los
/// titulos livianos (precios, pasos de "Por que Arlani", vitrina).
TextStyle bricolage({double size = 24, FontWeight weight = FontWeight.w400, Color color = Colors.white, double? height}) =>
    GoogleFonts.bricolageGrotesque(fontSize: size, fontWeight: weight, color: color, height: height);
