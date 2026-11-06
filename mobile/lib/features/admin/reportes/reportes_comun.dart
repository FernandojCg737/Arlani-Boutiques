import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/api_client.dart';

/// Formatos de exportacion: los mismos de la web (core/reporte_export.py).
const formatosReporte = {'pdf': 'PDF', 'excel': 'Excel', 'csv': 'CSV', 'html': 'HTML'};
const _extension = {'pdf': 'pdf', 'excel': 'xlsx', 'csv': 'csv', 'html': 'html'};

/// Exportar un reporte: elegir formato y compartir/guardar el archivo o
/// enviarlo por correo como adjunto. `ruta` + `params` para los reportes fijos
/// (GET .../exportar); `tabla` para el dinamico y el de voz (POST exportar-tabla).
Future<void> exportarReporte(
  BuildContext context,
  Dio dio, {
  required String nombre,
  String? ruta,
  Map<String, dynamic>? params,
  Map<String, dynamic>? tabla,
  String? correoInicial,
}) async {
  String formato = 'pdf';
  final correo = TextEditingController(text: correoInicial ?? '');
  final accion = await showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, refrescar) => Padding(
        padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + MediaQuery.viewInsetsOf(ctx).bottom),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Exportar · $nombre', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
          const SizedBox(height: 12),
          Wrap(spacing: 8, children: [
            for (final f in formatosReporte.entries)
              ChoiceChip(label: Text(f.value), selected: formato == f.key, onSelected: (_) => refrescar(() => formato = f.key)),
          ]),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => Navigator.pop(ctx, 'compartir'),
            icon: const Icon(Icons.ios_share),
            label: const Text('COMPARTIR O GUARDAR'),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: correo,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(labelText: 'Enviar a este correo', prefixIcon: Icon(Icons.mail_outline)),
          ),
          const SizedBox(height: 8),
          OutlinedButton(onPressed: () => Navigator.pop(ctx, 'correo'), child: const Text('ENVIAR POR CORREO')),
        ]),
      ),
    ),
  );
  if (accion == null || !context.mounted) return;
  final mensajero = ScaffoldMessenger.of(context);
  final email = correo.text.trim();
  if (accion == 'correo' && !RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
    mensajero.showSnackBar(const SnackBar(content: Text('Escribe un correo válido.')));
    return;
  }
  mensajero.showSnackBar(SnackBar(content: Text(accion == 'correo' ? 'Enviando el reporte…' : 'Preparando el archivo…')));
  try {
    final porCorreo = accion == 'correo';
    final Response res = ruta != null
        ? await dio.get(ruta,
            queryParameters: {...?params, 'formato': formato, if (porCorreo) 'correo': email},
            options: Options(responseType: porCorreo ? ResponseType.json : ResponseType.bytes))
        : await dio.post('/reportes/exportar-tabla',
            data: {'tabla': tabla, 'formato': formato, if (porCorreo) 'correo': email},
            options: Options(responseType: porCorreo ? ResponseType.json : ResponseType.bytes));
    if (porCorreo) {
      mensajero.showSnackBar(SnackBar(content: Text('Te enviamos el reporte a $email.')));
      return;
    }
    final dir = await getTemporaryDirectory();
    final limpio = nombre.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-');
    final archivo = File('${dir.path}/$limpio.${_extension[formato]}');
    await archivo.writeAsBytes(res.data as List<int>);
    await SharePlus.instance.share(ShareParams(files: [XFile(archivo.path)], subject: nombre));
  } catch (e) {
    mensajero.showSnackBar(SnackBar(content: Text(extractErrorMessage(e))));
  }
}

/// Tabla de un reporte (dinamico o por voz): columnas, filas y totales, que
/// se desliza a los lados como en la web.
class TablaReporteVista extends StatelessWidget {
  const TablaReporteVista({super.key, required this.tabla});
  final Map<String, dynamic> tabla;

  String _valor(dynamic v, String tipo) {
    if (v == null) return '—';
    if (tipo == 'moneda') return 'Bs ${(double.tryParse('$v') ?? 0).toStringAsFixed(2)}';
    if (tipo == 'numero' && v is num) return v % 1 == 0 ? '${v.toInt()}' : v.toStringAsFixed(2);
    return '$v';
  }

  @override
  Widget build(BuildContext context) {
    final columnas = (tabla['columnas'] as List).cast<Map<String, dynamic>>();
    final filas = (tabla['filas'] as List).cast<Map<String, dynamic>>();
    final totales = tabla['totales'] as Map<String, dynamic>?;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(tabla['titulo'].toString(), style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
      if (tabla['subtitulo'] != null) Text(tabla['subtitulo'].toString(), style: const TextStyle(fontSize: 12.5, color: Colors.black54)),
      const SizedBox(height: 8),
      if (filas.isEmpty)
        const Padding(padding: EdgeInsets.all(16), child: Text('No hay datos para este reporte.'))
      else
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            headingRowHeight: 40,
            dataRowMinHeight: 36,
            dataRowMaxHeight: 52,
            columns: [for (final c in columnas) DataColumn(label: Text(c['etiqueta'].toString().toUpperCase()), numeric: c['tipo'] != 'texto')],
            rows: [
              for (final f in filas)
                DataRow(cells: [for (final c in columnas) DataCell(Text(_valor(f[c['clave']], c['tipo'].toString())))]),
              if (totales != null)
                DataRow(
                  color: const WidgetStatePropertyAll(Color(0xFFF4F1EE)),
                  cells: [
                    for (var i = 0; i < columnas.length; i++)
                      DataCell(Text(
                        i == 0 ? 'TOTAL' : _valor(totales[columnas[i]['clave']], columnas[i]['tipo'].toString()),
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      )),
                  ],
                ),
            ],
          ),
        ),
    ]);
  }
}
