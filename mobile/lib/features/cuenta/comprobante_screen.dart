import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../../core/api_config.dart';
import '../../widgets/whatsapp_float_button.dart';
import '../auth/auth_provider.dart';
import '../portada/encabezado_plataforma.dart';
import '../portada/estilo_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../storefront/catalogo_provider.dart';
import 'cuenta_repository.dart' show fechaDelBackend;

const _metodo = {
  'paypal': 'PayPal / Tarjeta de crédito',
  'qr': 'QR',
  'transferencia': 'Transferencia bancaria',
  'otro': 'Otro',
  'efectivo': 'Efectivo en sucursal',
};
const _estadoPago = {
  'completado': 'Pagado',
  'verificando': 'Comprobante en revisión',
  'rechazado': 'Pago rechazado',
  'pendiente': 'Pendiente',
};
const _meses = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

double _num(Object? v) => v == null ? 0 : num.parse(v.toString()).toDouble();
String _bs(double v) => '${v.toStringAsFixed(2)} Bs';

class _Detalle {
  _Detalle(Map<String, dynamic> j)
      : producto = j['producto_nombre'] as String,
        talla = j['talla_codigo'] as String,
        color = j['color_nombre'] as String,
        cantidad = j['cantidad'] as int,
        precio = _num(j['precio_unitario']);

  final String producto;
  final String talla;
  final String color;
  final int cantidad;
  final double precio;
  double get subtotal => precio * cantidad;
}

class _Comprobante {
  _Comprobante(Map<String, dynamic> j)
      : id = j['id'] as int,
        tipo = j['tipo'] as String,
        sucursal = j['sucursal_nombre'] as String,
        fecha = fechaDelBackend(j['fecha']!),
        total = _num(j['total']),
        metodoPago = j['metodo_pago'] as String? ?? '',
        metodoPagoNombre = j['metodo_pago_nombre'] as String?,
        motivoRechazo = j['motivo_rechazo'] as String?,
        estadoPago = j['estado_pago'] as String? ?? '',
        atendidoPor = j['atendido_por_nombre'] as String?,
        facturaNombre = j['factura_nombre'] as String?,
        facturaNit = j['factura_nit'] as String?,
        tienda = j['tienda'] as Map<String, dynamic>?,
        detalles = [for (final d in (j['detalles'] as List<dynamic>).cast<Map<String, dynamic>>()) _Detalle(d)];

  final int id;
  final String tipo;
  final String sucursal;
  final DateTime fecha;
  final double total;
  final String metodoPago;
  final String? metodoPagoNombre;
  final String? motivoRechazo;
  final String estadoPago;
  final String? atendidoPor;
  final String? facturaNombre;
  final String? facturaNit;
  final Map<String, dynamic>? tienda;
  final List<_Detalle> detalles;

  String? _t(String k) {
    final v = tienda?[k];
    return v is String && v.isNotEmpty ? v : null;
  }

  String get tiendaNombre => _t('nombre') ?? 'Arlani Boutiques';
  String? get logo => _t('logo_url');
  String get folio => '$id'.padLeft(6, '0');
  String get fechaTexto {
    final h = fecha.hour % 12 == 0 ? 12 : fecha.hour % 12;
    return '${fecha.day} de ${_meses[fecha.month - 1]} de ${fecha.year}, $h:${fecha.minute.toString().padLeft(2, '0')} ${fecha.hour < 12 ? 'AM' : 'PM'}';
  }

  List<String> get datosTienda => [
        if (_t('razon_social') != null) _t('razon_social')!,
        if (_t('nit') != null) 'NIT ${_t('nit')}',
        '${_t('direccion_fiscal') ?? sucursal}${_t('ciudad') != null ? ', ${_t('ciudad')}' : ''}, Bolivia',
        if (_t('telefono') != null || _t('email_contacto') != null)
          [_t('telefono'), _t('email_contacto')].whereType<String>().join(' · '),
      ];

  List<String> get info => [
        if (facturaNit != null || facturaNombre != null) 'Factura a: ${facturaNombre ?? 'tu nombre'} · NIT / CI ${facturaNit ?? 'S/N'}',
        'Sucursal: $sucursal',
        'Tipo: ${tipo == 'venta_digital' ? 'Compra en línea' : 'Compra en tienda'}',
        if (atendidoPor != null) 'Atendido por: $atendidoPor',
        'Método de pago: ${metodoPagoNombre ?? _metodo[metodoPago] ?? metodoPago}',
      ];

  String get estadoTexto => 'Estado: ${_estadoPago[estadoPago] ?? estadoPago}';
}

final _comprobanteProvider = FutureProvider.autoDispose.family<_Comprobante, int>((ref, id) async {
  final res = await ref.watch(apiClientProvider).dio.get('/ventas/mias/$id');
  return _Comprobante(res.data as Map<String, dynamic>);
});

/// Comprobante de una compra (`pages/comprobante` de la web): el documento
/// de la tienda que vendio, con su logo, color y datos fiscales. "Descargar /
/// Imprimir" arma el PDF en el telefono (guardar, compartir o imprimir).
class ComprobanteScreen extends ConsumerWidget {
  const ComprobanteScreen({super.key, required this.ventaId});

  final int ventaId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final arriba = MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto;
    final datos = ref.watch(_comprobanteProvider(ventaId));
    void irA(SeccionPortada s) => context.go(s == SeccionPortada.inicio ? '/' : '/?seccion=${s.name}');

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: Plataforma.marfil,
        body: Stack(
          children: [
            SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(20, arriba + 36, 20, 80),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Align(
                    alignment: Alignment.centerLeft,
                    child: InkWell(
                      onTap: () => context.canPop() ? context.pop() : context.go('/perfil?tab=compras'),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.arrow_back, size: 16, color: Color(0xFF121A2C)),
                            const SizedBox(width: 6),
                            Text('VOLVER A MI PERFIL',
                                style: GoogleFonts.inter(
                                    fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5, color: const Color(0xFF121A2C))),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  datos.when(
                    loading: () => const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator())),
                    error: (_, _) => Text('No pudimos encontrar esa compra.',
                        style: GoogleFonts.inter(fontSize: 14, color: const Color(0xFF666666))),
                    data: (c) => _Documento(c),
                  ),
                ],
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: EncabezadoPlataforma(
                solido: true,
                pleno: true,
                onIrA: irA,
                onBuscar: (texto) {
                  ref.read(tiendaFiltrosProvider.notifier).setBusqueda(texto.trim());
                  context.go('/catalogo');
                },
              ),
            ),
            Positioned(right: 16, bottom: 16 + MediaQuery.paddingOf(context).bottom, child: const WhatsappFloatButton()),
          ],
        ),
      ),
    );
  }
}

class _Documento extends StatelessWidget {
  const _Documento(this.c);

  final _Comprobante c;

  @override
  Widget build(BuildContext context) {
    // El color de la tienda, oscurecido lo justo para leerse (como la web).
    final marca = c.tienda == null ? const Color(0xFF203C40) : colorMarca(c.tienda!['color_marca'] as String?);
    final colorEstado = switch (c.estadoPago) {
      'verificando' || 'pendiente' => const Color(0xFFA86B00),
      'rechazado' => const Color(0xFFB3261E),
      _ => const Color(0xFF2E7D32),
    };
    final gris = GoogleFonts.inter(fontSize: 11.5, height: 1.45, color: const Color(0xFF888888));

    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: const Color(0xFFEEEEEE))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // `.comprobante__header`: la tienda y el folio.
          Container(
            padding: const EdgeInsets.only(bottom: 20),
            decoration: BoxDecoration(border: Border(bottom: BorderSide(color: marca, width: 3))),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (c.logo != null) ...[
                      SizedBox(width: 56, height: 56, child: ImagenTienda(c.logo!, width: 56, height: 56)),
                      const SizedBox(width: 12),
                    ],
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(c.tiendaNombre, style: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w800, color: marca)),
                          for (final d in c.datosTienda) Text(d, style: gris),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Text('COMPROBANTE DE COMPRA',
                    style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.8, color: const Color(0xFF999999))),
                Text('N° ${c.folio}', style: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.w800, color: marca)),
                Text(c.fechaTexto, style: gris),
              ],
            ),
          ),
          const SizedBox(height: 18),
          for (final linea in c.info)
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Text(linea, style: GoogleFonts.inter(fontSize: 13, color: const Color(0xFF777777))),
            ),
          Text(c.estadoTexto, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w700, color: colorEstado)),
          if (c.estadoPago == 'rechazado' && c.motivoRechazo != null)
            Text('Motivo: ${c.motivoRechazo}', style: GoogleFonts.inter(fontSize: 13, color: const Color(0xFFB3261E))),
          const SizedBox(height: 18),
          // Las prendas (la tabla de la web, en filas para el celular).
          Container(
            padding: const EdgeInsets.only(bottom: 8),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE), width: 2))),
            child: Row(
              children: [
                Expanded(child: Text('PRODUCTO', style: _encabezadoTabla)),
                Text('SUBTOTAL', style: _encabezadoTabla),
              ],
            ),
          ),
          for (final d in c.detalles)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFF2F2F2)))),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(d.producto, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: marca)),
                        Text('Talla ${d.talla} · ${d.color} · ${d.cantidad} × ${_bs(d.precio)}', style: gris),
                      ],
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(_bs(d.subtotal), style: GoogleFonts.inter(fontSize: 13, color: marca)),
                ],
              ),
            ),
          Container(
            margin: const EdgeInsets.only(top: 16),
            padding: const EdgeInsets.only(top: 14),
            decoration: BoxDecoration(border: Border(top: BorderSide(color: marca, width: 3))),
            child: Row(
              children: [
                Expanded(child: Text('TOTAL', style: _encabezadoTabla.copyWith(fontSize: 12))),
                Text(_bs(c.total), style: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w800, color: marca)),
              ],
            ),
          ),
          const SizedBox(height: 22),
          Text('Gracias por tu compra en ${c.tiendaNombre}.',
              textAlign: TextAlign.center, style: GoogleFonts.inter(fontSize: 13, color: marca)),
          const SizedBox(height: 6),
          Text(
            'Este documento es un comprobante interno de compra y no reemplaza una factura fiscal con validez tributaria (NIT).',
            textAlign: TextAlign.center,
            style: GoogleFonts.inter(fontSize: 10, height: 1.4, color: const Color(0xFFAAAAAA)),
          ),
          const SizedBox(height: 22),
          Center(
            child: FilledButton.icon(
              onPressed: () => Printing.layoutPdf(name: 'comprobante-${c.folio}.pdf', onLayout: (_) => _pdf(c, marca)),
              icon: const Icon(Icons.download_outlined, size: 18),
              label: const Text('DESCARGAR / IMPRIMIR'),
              style: FilledButton.styleFrom(
                backgroundColor: marca,
                foregroundColor: Colors.white,
                shape: const RoundedRectangleBorder(),
                padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 16),
                textStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.6),
              ),
            ),
          ),
        ],
      ),
    );
  }

  static final _encabezadoTabla =
      GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: const Color(0xFF999999));
}

/// El mismo comprobante en PDF (A4), para guardar, compartir o imprimir.
Future<Uint8List> _pdf(_Comprobante c, Color marca) async {
  final color = PdfColor.fromInt(marca.toARGB32());
  final gris = PdfColor.fromInt(0xFF888888);
  pw.ImageProvider? logo;
  if (c.logo != null) {
    try {
      logo = await networkImage(resolveImageUrl(c.logo!));
    } catch (_) {
      // Sin logo: el comprobante sale igual.
    }
  }
  final doc = pw.Document(title: 'Comprobante ${c.folio}', author: c.tiendaNombre);
  doc.addPage(
    pw.MultiPage(
      pageFormat: PdfPageFormat.a4,
      margin: const pw.EdgeInsets.all(36),
      build: (_) => [
        pw.Container(
          padding: const pw.EdgeInsets.only(bottom: 16),
          decoration: pw.BoxDecoration(border: pw.Border(bottom: pw.BorderSide(color: color, width: 3))),
          child: pw.Row(
            crossAxisAlignment: pw.CrossAxisAlignment.start,
            children: [
              if (logo != null) ...[pw.SizedBox(width: 56, height: 56, child: pw.Image(logo)), pw.SizedBox(width: 12)],
              pw.Expanded(
                child: pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.start,
                  children: [
                    pw.Text(c.tiendaNombre, style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold, color: color)),
                    for (final d in c.datosTienda) pw.Text(d, style: pw.TextStyle(fontSize: 9, color: gris)),
                  ],
                ),
              ),
              pw.Column(
                crossAxisAlignment: pw.CrossAxisAlignment.end,
                children: [
                  pw.Text('COMPROBANTE DE COMPRA', style: pw.TextStyle(fontSize: 8, fontWeight: pw.FontWeight.bold, color: gris)),
                  pw.Text('N° ${c.folio}', style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold, color: color)),
                  pw.Text(c.fechaTexto, style: pw.TextStyle(fontSize: 9, color: gris)),
                ],
              ),
            ],
          ),
        ),
        pw.SizedBox(height: 14),
        for (final linea in [...c.info, c.estadoTexto, if (c.estadoPago == 'rechazado' && c.motivoRechazo != null) 'Motivo: ${c.motivoRechazo}'])
          pw.Text(linea, style: pw.TextStyle(fontSize: 10, color: PdfColor.fromInt(0xFF555555))),
        pw.SizedBox(height: 14),
        pw.TableHelper.fromTextArray(
          headers: ['Producto', 'Talla', 'Color', 'Cant.', 'Precio', 'Subtotal'],
          data: [
            for (final d in c.detalles) [d.producto, d.talla, d.color, '${d.cantidad}', _bs(d.precio), _bs(d.subtotal)],
          ],
          headerStyle: pw.TextStyle(fontSize: 8, fontWeight: pw.FontWeight.bold, color: gris),
          cellStyle: pw.TextStyle(fontSize: 9, color: color),
          headerDecoration: const pw.BoxDecoration(),
          border: null,
          rowDecoration: pw.BoxDecoration(border: pw.Border(bottom: pw.BorderSide(color: PdfColor.fromInt(0xFFEEEEEE)))),
          cellAlignments: {3: pw.Alignment.center, 4: pw.Alignment.centerRight, 5: pw.Alignment.centerRight},
        ),
        pw.Container(
          margin: const pw.EdgeInsets.only(top: 12),
          padding: const pw.EdgeInsets.only(top: 10),
          decoration: pw.BoxDecoration(border: pw.Border(top: pw.BorderSide(color: color, width: 3))),
          child: pw.Row(
            mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
            children: [
              pw.Text('TOTAL', style: pw.TextStyle(fontSize: 10, fontWeight: pw.FontWeight.bold, color: gris)),
              pw.Text(_bs(c.total), style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold, color: color)),
            ],
          ),
        ),
        pw.SizedBox(height: 24),
        pw.Center(child: pw.Text('Gracias por tu compra en ${c.tiendaNombre}.', style: pw.TextStyle(fontSize: 10, color: color))),
        pw.SizedBox(height: 4),
        pw.Center(
          child: pw.Text(
            'Este documento es un comprobante interno de compra y no reemplaza una factura fiscal con validez tributaria (NIT).',
            textAlign: pw.TextAlign.center,
            style: pw.TextStyle(fontSize: 7, color: PdfColor.fromInt(0xFFAAAAAA)),
          ),
        ),
      ],
    ),
  );
  return doc.save();
}
