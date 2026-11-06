import 'package:flutter/material.dart';

/// Un campo del formulario en dialogo.
class CampoDialogo {
  const CampoDialogo(this.clave, this.etiqueta, {this.numero = false, this.lineas = 1, this.inicial = '', this.ayuda});
  final String clave;
  final String etiqueta;
  final bool numero;
  final int lineas;
  final String inicial;
  final String? ayuda;
}

/// Formulario corto en un dialogo (abrir caja, retiro, motivo...). Devuelve
/// los valores por clave o null si se cancelo.
Future<Map<String, String>?> formularioDialogo(
  BuildContext context, {
  required String titulo,
  String? texto,
  required List<CampoDialogo> campos,
  String aceptar = 'Guardar',
}) {
  final controles = {for (final c in campos) c.clave: TextEditingController(text: c.inicial)};
  return showDialog<Map<String, String>>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(titulo),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (texto != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(texto)),
          for (final c in campos)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: TextField(
                controller: controles[c.clave],
                keyboardType: c.numero ? const TextInputType.numberWithOptions(decimal: true) : TextInputType.text,
                maxLines: c.lineas,
                decoration: InputDecoration(labelText: c.etiqueta, helperText: c.ayuda),
              ),
            ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, {for (final e in controles.entries) e.key: e.value.text.trim()}),
          child: Text(aceptar),
        ),
      ],
    ),
  );
}

Future<bool> confirmarDialogo(BuildContext context, String texto, {String si = 'Sí', bool peligro = false}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      content: Text(texto),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('No')),
        TextButton(
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(si, style: TextStyle(color: peligro ? const Color(0xFFB3261E) : null, fontWeight: FontWeight.w700)),
        ),
      ],
    ),
  );
  return r ?? false;
}

String bsTexto(dynamic v) => 'Bs ${double.tryParse('$v')?.toStringAsFixed(2) ?? '0.00'}';

String fechaTexto(dynamic v, {bool hora = true}) {
  if (v == null) return '—';
  final s = v.toString();
  final f = (s.length > 10
          ? DateTime.parse(RegExp(r'([zZ]|[+-]\d\d:?\d\d)$').hasMatch(s) ? s : '${s}Z')
          : DateTime.parse(s))
      .toLocal();
  String dos(int n) => n.toString().padLeft(2, '0');
  final d = '${dos(f.day)}/${dos(f.month)}/${f.year}';
  return hora && s.length > 10 ? '$d ${dos(f.hour)}:${dos(f.minute)}' : d;
}
