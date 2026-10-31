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

const _motivo = {'talla': 'Talla', 'color': 'Color', 'modelo': 'Otro modelo', 'defecto': 'Defecto', 'otro': 'Otro'};
const _estado = {
  'solicitado': 'Por revisar',
  'por_pagar': 'Espera el pago de la diferencia',
  'verificando': 'Comprobante por revisar',
  'completado': 'Completado',
  'rechazado': 'Rechazado',
  'cancelado': 'Cancelado por el cliente',
};
const _meses = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

double _num(Object? v) => v == null ? 0 : num.parse(v.toString()).toDouble();
String _bs(double v) => '${v.toStringAsFixed(2)} Bs';

class _Cambio {
  _Cambio(Map<String, dynamic> j)
      : id = j['id'] as int,
        ventaId = j['venta_id'] as int,
        ventaFecha = fechaDelBackend(j['venta_fecha']!),
        estado = j['estado'] as String,
        motivo = j['motivo'] as String,
        cantidad = j['cantidad'] as int,
        sucursal = j['sucursal_nombre'] as String,
        cliente = j['cliente_nombre'] as String,
        clienteEmail = j['cliente_email'] as String,
        productoOriginal = j['producto_original'] as String,
        tallaOriginal = j['talla_original'] as String,
        colorOriginal = j['color_original'] as String,
        productoNuevo = j['producto_nuevo'] as String,
        tallaNueva = j['talla_nueva'] as String,
        colorNuevo = j['color_nuevo'] as String,
        precioPagado = _num(j['precio_pagado']),
        precioNuevo = _num(j['precio_nuevo']),
        diferencia = _num(j['diferencia']),
        reembolsoMetodo = j['reembolso_metodo'] as String?,
        metodoPagoNombre = j['metodo_pago_nombre'] as String?,
        empleado = j['empleado_nombre'] as String?,
        fecha = fechaDelBackend(j['fecha_completado'] ?? j['fecha_solicitud']!),
        tienda = (j['tienda'] as Map<String, dynamic>?) ?? const {};

  final int id;
  final int ventaId;
  final DateTime ventaFecha;
  final String estado;
  final String motivo;
  final int cantidad;
  final String sucursal;
  final String cliente;
  final String clienteEmail;
  final String productoOriginal;
  final String tallaOriginal;
  final String colorOriginal;
  final String productoNuevo;
  final String tallaNueva;
  final String colorNuevo;
  final double precioPagado;
  final double precioNuevo;
  final double diferencia;
  final String? reembolsoMetodo;
  final String? metodoPagoNombre;
  final String? empleado;
  final DateTime fecha;
  final Map<String, dynamic> tienda;

  String? _t(String k) {
    final v = tienda[k];
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
        'Cliente: $cliente · $clienteEmail',
        'Compra original: N° $ventaId del ${ventaFecha.day}/${ventaFecha.month}/${ventaFecha.year}',
        'Sucursal: $sucursal',
        'Motivo: ${_motivo[motivo] ?? motivo}',
        if (empleado != null) 'Atendido por: $empleado',
      ];

  String get estadoTexto => 'Estado: ${_estado[estado] ?? estado}';

  /// (texto, monto) del total: lo que pago, lo que se le devolvio o nada.
  (String, double) get total {
    if (diferencia > 0) return ('Pagaste la diferencia${metodoPagoNombre != null ? ' ($metodoPagoNombre)' : ''}', diferencia);
    if (diferencia < 0) {
      final como = reembolsoMetodo == null ? '' : reembolsoMetodo == 'paypal' ? ' (a tu PayPal)' : ' (en tienda)';
      return ('Te devolvimos$como', -diferencia);
    }
    return ('Diferencia', 0);
  }
}

final _cambioProvider = FutureProvider.autoDispose.family<_Cambio, int>((ref, id) async {
  final res = await ref.watch(apiClientProvider).dio.get('/cambios/mios/$id');
  return _Cambio(res.data as Map<String, dynamic>);
});

/// Comprobante de un cambio de prenda (`pages/comprobante-cambio` de la web):
/// lo que el cliente devolvio, lo que recibio y la diferencia, con los datos
/// de la tienda. "Descargar / Imprimir" arma el PDF.
class ComprobanteCambioScreen extends ConsumerWidget {
  const ComprobanteCambioScreen({super.key, required this.cambioId});

  final int cambioId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final arriba = MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto;
    final datos = ref.watch(_cambioProvider(cambioId));
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
                      onTap: () => context.canPop() ? context.pop() : context.go('/perfil?tab=cambios'),
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
                    error: (_, _) => Text('No pudimos encontrar ese cambio.',
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

  final _Cambio c;

  static final _encabezadoTabla =
      GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: const Color(0xFF999999));

  Widget _fila(String sentido, Color colorSentido, String producto, String talla, String color, double precio, String? nota, Color marca) {
    final gris = GoogleFonts.inter(fontSize: 11.5, height: 1.45, color: const Color(0xFF888888));
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFF2F2F2)))),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(sentido.toUpperCase(),
                    style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 0.6, color: colorSentido)),
                Text(producto, style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w600, color: marca)),
                Text('Talla $talla · $color · ${c.cantidad} × ${_bs(precio)}${nota ?? ''}', style: gris),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(_bs(precio * c.cantidad), style: GoogleFonts.inter(fontSize: 13, color: marca)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final marca = c.tienda.isEmpty ? const Color(0xFF203C40) : colorMarca(c.tienda['color_marca'] as String?);
    final gris = GoogleFonts.inter(fontSize: 11.5, height: 1.45, color: const Color(0xFF888888));
    final (textoTotal, montoTotal) = c.total;

    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: const Color(0xFFEEEEEE))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
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
                Text('COMPROBANTE DE CAMBIO',
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
          Text(c.estadoTexto,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: c.estado == 'completado' ? const Color(0xFF2E7D32) : const Color(0xFFA86B00),
              )),
          const SizedBox(height: 18),
          Container(
            padding: const EdgeInsets.only(bottom: 8),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE), width: 2))),
            child: Row(
              children: [
                Expanded(child: Text('PRENDA', style: _encabezadoTabla)),
                Text('SUBTOTAL', style: _encabezadoTabla),
              ],
            ),
          ),
          _fila('Devuelves', const Color(0xFFB3261E), c.productoOriginal, c.tallaOriginal, c.colorOriginal, c.precioPagado, ' (pagado)', marca),
          _fila('Recibes', const Color(0xFF2E7D32), c.productoNuevo, c.tallaNueva, c.colorNuevo, c.precioNuevo, null, marca),
          Container(
            margin: const EdgeInsets.only(top: 16),
            padding: const EdgeInsets.only(top: 14),
            decoration: BoxDecoration(border: Border(top: BorderSide(color: marca, width: 3))),
            child: Row(
              children: [
                Expanded(child: Text(textoTotal.toUpperCase(), style: _encabezadoTabla.copyWith(fontSize: 11))),
                Text(_bs(montoTotal), style: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w800, color: marca)),
              ],
            ),
          ),
          const SizedBox(height: 22),
          Text('Gracias por comprar en ${c.tiendaNombre}.', textAlign: TextAlign.center, style: GoogleFonts.inter(fontSize: 13, color: marca)),
          const SizedBox(height: 6),
          Text(
            'Cambio según la política de la tienda (hasta 24 horas después de la compra). Este documento es un comprobante interno y no reemplaza una factura fiscal con validez tributaria (NIT).',
            textAlign: TextAlign.center,
            style: GoogleFonts.inter(fontSize: 10, height: 1.4, color: const Color(0xFFAAAAAA)),
          ),
          const SizedBox(height: 22),
          Center(
            child: FilledButton.icon(
              onPressed: () => Printing.layoutPdf(name: 'comprobante-cambio-${c.folio}.pdf', onLayout: (_) => _pdf(c, marca)),
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
}

/// El mismo comprobante del cambio en PDF (A4).
Future<Uint8List> _pdf(_Cambio c, Color marca) async {
  final color = PdfColor.fromInt(marca.toARGB32());
  final gris = PdfColor.fromInt(0xFF888888);
  pw.ImageProvider? logo;
  if (c.logo != null) {
    try {
      logo = await networkImage(resolveImageUrl(c.logo!));
    } catch (_) {}
  }
  final (textoTotal, montoTotal) = c.total;
  final doc = pw.Document(title: 'Comprobante de cambio ${c.folio}', author: c.tiendaNombre);
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
                  pw.Text('COMPROBANTE DE CAMBIO', style: pw.TextStyle(fontSize: 8, fontWeight: pw.FontWeight.bold, color: gris)),
                  pw.Text('N° ${c.folio}', style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold, color: color)),
                  pw.Text(c.fechaTexto, style: pw.TextStyle(fontSize: 9, color: gris)),
                ],
              ),
            ],
          ),
        ),
        pw.SizedBox(height: 14),
        for (final linea in [...c.info, c.estadoTexto]) pw.Text(linea, style: pw.TextStyle(fontSize: 10, color: PdfColor.fromInt(0xFF555555))),
        pw.SizedBox(height: 14),
        pw.TableHelper.fromTextArray(
          headers: ['', 'Producto', 'Talla', 'Color', 'Cant.', 'Precio', 'Subtotal'],
          data: [
            ['Devuelves', c.productoOriginal, c.tallaOriginal, c.colorOriginal, '${c.cantidad}', '${_bs(c.precioPagado)} (pagado)', _bs(c.precioPagado * c.cantidad)],
            ['Recibes', c.productoNuevo, c.tallaNueva, c.colorNuevo, '${c.cantidad}', _bs(c.precioNuevo), _bs(c.precioNuevo * c.cantidad)],
          ],
          headerStyle: pw.TextStyle(fontSize: 8, fontWeight: pw.FontWeight.bold, color: gris),
          cellStyle: pw.TextStyle(fontSize: 9, color: color),
          headerDecoration: const pw.BoxDecoration(),
          border: null,
          rowDecoration: pw.BoxDecoration(border: pw.Border(bottom: pw.BorderSide(color: PdfColor.fromInt(0xFFEEEEEE)))),
          cellAlignments: {4: pw.Alignment.center, 5: pw.Alignment.centerRight, 6: pw.Alignment.centerRight},
        ),
        pw.Container(
          margin: const pw.EdgeInsets.only(top: 12),
          padding: const pw.EdgeInsets.only(top: 10),
          decoration: pw.BoxDecoration(border: pw.Border(top: pw.BorderSide(color: color, width: 3))),
          child: pw.Row(
            mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
            children: [
              pw.Text(textoTotal.toUpperCase(), style: pw.TextStyle(fontSize: 10, fontWeight: pw.FontWeight.bold, color: gris)),
              pw.Text(_bs(montoTotal), style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold, color: color)),
            ],
          ),
        ),
        pw.SizedBox(height: 24),
        pw.Center(child: pw.Text('Gracias por comprar en ${c.tiendaNombre}.', style: pw.TextStyle(fontSize: 10, color: color))),
        pw.SizedBox(height: 4),
        pw.Center(
          child: pw.Text(
            'Cambio según la política de la tienda (hasta 24 horas después de la compra). Este documento es un comprobante interno y no reemplaza una factura fiscal con validez tributaria (NIT).',
            textAlign: pw.TextAlign.center,
            style: pw.TextStyle(fontSize: 7, color: PdfColor.fromInt(0xFFAAAAAA)),
          ),
        ),
      ],
    ),
  );
  return doc.save();
}
