import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_config.dart';
import 'offline_modelos.dart';
import 'offline_servicio.dart';

/// Estilos de `sin-conexion.scss` y `ventas.scss` de la web, con el azul
/// oscuro del SaaS (Arlani) en botones, pestañas y titulos.
const marcaOffline = Color(0xFF121A2C);
const bordeOffline = Color(0xFFE5E2DF);
const ambarOffline = Color(0xFFB26A00);

String bs(double v) => v.toStringAsFixed(2).replaceAll('.', ',');

String fechaCorta(DateTime d) {
  final l = d.toLocal();
  String dos(int n) => n.toString().padLeft(2, '0');
  return '${dos(l.day)}/${dos(l.month)}/${l.year} ${dos(l.hour)}:${dos(l.minute)}';
}

TextStyle textoOffline({double size = 13, FontWeight peso = FontWeight.w400, Color color = const Color(0xFF333333)}) =>
    GoogleFonts.inter(fontSize: size, fontWeight: peso, color: color, height: 1.45);

Widget subOffline(String t) => Padding(
  padding: const EdgeInsets.only(top: 2),
  child: Text(t, style: textoOffline(size: 12, color: const Color(0xFF777777))),
);

Widget tituloSeccionOffline(String t) => Padding(
  padding: const EdgeInsets.fromLTRB(0, 24, 0, 8),
  child: Text(
    t.toUpperCase(),
    style: textoOffline(size: 12, peso: FontWeight.w800, color: marcaOffline),
  ),
);

/// `.admin-content__header`: titulo y explicacion.
class CabeceraOffline extends StatelessWidget {
  const CabeceraOffline({super.key, this.eyebrow, required this.titulo, required this.texto});
  final String? eyebrow;
  final String titulo;
  final String texto;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (eyebrow != null)
        Text(
          eyebrow!.toUpperCase(),
          style: textoOffline(size: 11, peso: FontWeight.w700, color: const Color(0xFF999999)),
        ),
      Text(
        titulo,
        style: GoogleFonts.playfairDisplay(fontSize: 26, fontWeight: FontWeight.w600, color: marcaOffline),
      ),
      const SizedBox(height: 6),
      Text(texto, style: textoOffline(color: const Color(0xFF666666))),
      const SizedBox(height: 14),
    ],
  );
}

/// `.ventas-nueva-btn`: boton oscuro en mayusculas.
class BotonOffline extends StatelessWidget {
  const BotonOffline(this.texto, {super.key, this.onPressed, this.ancho = false});
  final String texto;
  final VoidCallback? onPressed;
  final bool ancho;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: ancho ? double.infinity : null,
    child: FilledButton(
      style: FilledButton.styleFrom(
        backgroundColor: marcaOffline,
        disabledBackgroundColor: const Color(0xFFB9BCC4),
        foregroundColor: Colors.white,
        shape: const RoundedRectangleBorder(),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      onPressed: onPressed,
      child: Text(texto.toUpperCase(), style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5)),
    ),
  );
}

/// `.offline-estado`: verde con conexion, ambar sin ella, y "Enviar ahora".
class BarraConexion extends ConsumerWidget {
  const BarraConexion({super.key, this.personal = false});
  final bool personal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(offlineProvider);
    final (fondo, tinta) = s.enLinea
        ? (const Color(0xFFEEF0F5), marcaOffline)
        : (const Color(0xFFFFF4E0), const Color(0xFF8A4F00));
    final n = s.pendientes;
    var detalle = n == 0 && personal
        ? 'Nada pendiente de enviar'
        : '$n ${n == 1 ? 'operación pendiente' : 'operaciones pendientes'} de enviar';
    if (personal && s.conflictos > 0) detalle += ' · ${s.conflictos} en conflicto';
    return Container(
      color: fondo,
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
      margin: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Container(
            width: 9,
            height: 9,
            decoration: BoxDecoration(color: tinta, shape: BoxShape.circle),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(
                    text: s.enLinea ? 'Con conexión' : 'Sin conexión',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  TextSpan(text: ' · $detalle'),
                ],
              ),
              style: textoOffline(size: 12.5, color: tinta),
            ),
          ),
          TextButton(
            style: TextButton.styleFrom(foregroundColor: tinta),
            onPressed: !s.enLinea || s.ocupado ? null : () => ref.read(offlineProvider).sincronizar(),
            child: Text(
              s.ocupado ? (personal ? 'Sincronizando…' : 'Enviando…') : (personal ? 'Sincronizar' : 'Enviar ahora'),
              style: const TextStyle(fontWeight: FontWeight.w700, decoration: TextDecoration.underline),
            ),
          ),
        ],
      ),
    );
  }
}

/// `.admin-error` / `.offline-aviso`.
class AvisoOffline extends StatelessWidget {
  const AvisoOffline(this.texto, {super.key, this.error = false});
  final String texto;
  final bool error;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 12),
    padding: const EdgeInsets.all(12),
    color: error ? const Color(0xFFFDECEA) : const Color(0xFFF1F5FF),
    child: Text(texto, style: textoOffline(size: 12.5, color: error ? const Color(0xFFB3261E) : const Color(0xFF1F2A44))),
  );
}

/// `.offline-chip--{estado}`.
class ChipEstado extends StatelessWidget {
  const ChipEstado(this.estado, {super.key, this.texto});
  final String estado;
  final String? texto;

  @override
  Widget build(BuildContext context) {
    final (fondo, tinta) = switch (estado) {
      'pendiente' ||
      'enviando' ||
      'error' ||
      'por_pagar' ||
      'por_cobrar' ||
      'pago_parcial' => (const Color(0xFFFFF4E0), ambarOffline),
      'confirmada' || 'resuelta' || 'pagada' => (const Color(0xFFEEF0F5), marcaOffline),
      'conflicto' || 'sin_stock' || 'no_pagada' => (const Color(0xFFFDECEA), const Color(0xFFB3261E)),
      'rechazada' || 'anulada' || 'cancelada' => (const Color(0xFFEEEEEE), const Color(0xFF666666)),
      _ => (const Color(0xFFF1F1F1), const Color(0xFF555555)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      color: fondo,
      child: Text(
        (texto ?? estadoOperacion[estado] ?? estado).toUpperCase(),
        style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 0.5, color: tinta),
      ),
    );
  }
}

/// `.mostrador-opcion`: boton de opcion (talla, modo, entrega, pago...).
class OpcionOffline extends StatelessWidget {
  const OpcionOffline({super.key, required this.texto, this.sub, required this.activa, this.onTap});
  final String texto;
  final String? sub;
  final bool activa;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final apagada = onTap == null;
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: activa ? marcaOffline : (apagada ? const Color(0xFFF5F5F5) : Colors.white),
          border: Border.all(color: activa ? marcaOffline : const Color(0xFFDDDDDD)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              texto,
              style: textoOffline(
                peso: FontWeight.w700,
                color: activa ? Colors.white : (apagada ? const Color(0xFFAAAAAA) : marcaOffline),
              ),
            ),
            if (sub != null) Text(sub!, style: textoOffline(size: 11, color: activa ? Colors.white70 : const Color(0xFF888888))),
          ],
        ),
      ),
    );
  }
}

Widget etiquetaOffline(String t) => Padding(
  padding: const EdgeInsets.only(top: 12, bottom: 6),
  child: Text(
    t.toUpperCase(),
    style: textoOffline(size: 11, peso: FontWeight.w700, color: const Color(0xFF888888)),
  ),
);

/// Foto de la prenda: la guardada en el telefono, la de internet o la inicial.
class FotoPrenda extends ConsumerWidget {
  const FotoPrenda({super.key, required this.url, required this.nombre});
  final String? url;
  final String nombre;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(offlineProvider);
    final local = s.fotoLocal(url);
    final inicial = Container(
      color: const Color(0xFFF3F3F1),
      alignment: Alignment.center,
      child: Text(
        nombre.isEmpty ? '?' : nombre[0],
        style: textoOffline(size: 28, peso: FontWeight.w700, color: const Color(0xFFAAAAAA)),
      ),
    );
    if (local != null) return Image.file(local, fit: BoxFit.cover, errorBuilder: (_, _, _) => inicial);
    if (url == null || !s.enLinea) return inicial;
    return CachedNetworkImage(imageUrl: resolveImageUrl(url!), fit: BoxFit.cover, errorWidget: (_, _, _) => inicial);
  }
}

/// `.mostrador-catalogo`: grilla de prendas; al elegir una se ve su talla y color.
class CatalogoOffline extends StatefulWidget {
  const CatalogoOffline({
    super.key,
    required this.productos,
    required this.disponible,
    required this.alAgregar,
    this.bloquearSinStock = false,
  });

  final List<ProductoLocal> productos;
  final int Function(ProductoLocal, VarianteLocal) disponible;
  final void Function(ProductoLocal, VarianteLocal, int) alAgregar;
  final bool bloquearSinStock;

  @override
  State<CatalogoOffline> createState() => _CatalogoOfflineState();
}

class _CatalogoOfflineState extends State<CatalogoOffline> {
  String _buscar = '';
  int? _productoId;

  /// En celular, la talla y el color se eligen en una hoja desde abajo (junto
  /// a la prenda tocada); en pantalla ancha, debajo de la grilla como en la web.
  void _elegirProducto(ProductoLocal p) {
    setState(() => _productoId = p.productoId);
    if (MediaQuery.sizeOf(context).width >= 840) return;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(),
      // A todo el ancho del celular (Material 3 la limita por defecto).
      constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(ctx).bottom),
          child: SingleChildScrollView(
            child: SizedBox(
              width: double.infinity,
              child: ElegirVariante(
                producto: p,
                disponible: widget.disponible,
                alAgregar: (v, n) {
                  widget.alAgregar(p, v, n);
                  Navigator.pop(ctx);
                },
              ),
            ),
          ),
        ),
      ),
    ).whenComplete(() {
      if (mounted) setState(() => _productoId = null);
    });
  }

  @override
  Widget build(BuildContext context) {
    final q = _buscar.trim().toLowerCase();
    final lista = widget.productos
        .where((p) => q.isEmpty || p.nombre.toLowerCase().contains(q) || (p.categoria ?? '').toLowerCase().contains(q))
        .toList();
    final ancho = MediaQuery.sizeOf(context).width;
    final sel = ancho < 840 ? null : widget.productos.where((p) => p.productoId == _productoId).firstOrNull;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          decoration: const InputDecoration(
            hintText: 'Buscar prenda…',
            prefixIcon: Icon(Icons.search, size: 20),
            isDense: true,
            border: OutlineInputBorder(borderRadius: BorderRadius.zero),
          ),
          onChanged: (v) => setState(() => _buscar = v),
        ),
        const SizedBox(height: 10),
        if (lista.isEmpty)
          subOffline('No hay prendas con stock conocido en esta sucursal.')
        else
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: ancho < 420 ? 2 : (ancho < 700 ? 3 : 4),
              mainAxisSpacing: 8,
              crossAxisSpacing: 8,
              childAspectRatio: 0.68,
            ),
            itemCount: lista.length,
            itemBuilder: (_, i) {
              final p = lista[i];
              final activa = p.productoId == _productoId;
              final bloqueada = widget.bloquearSinStock && p.stockTotal < 1;
              return InkWell(
                onTap: bloqueada ? null : () => _elegirProducto(p),
                child: Opacity(
                  opacity: bloqueada ? 0.45 : 1,
                  child: Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      border: Border.all(color: activa ? marcaOffline : bordeOffline, width: activa ? 2 : 1),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: SizedBox(
                            width: double.infinity,
                            child: FotoPrenda(url: p.imagenUrl, nombre: p.nombre),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          p.nombre,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: textoOffline(size: 12.5, peso: FontWeight.w700),
                        ),
                        Text('Bs ${bs(p.precio)}', style: textoOffline(size: 12, color: const Color(0xFF777777))),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        if (sel != null)
          Container(
            margin: const EdgeInsets.only(top: 12),
            decoration: BoxDecoration(
              color: const Color(0xFFFAFAF8),
              border: Border.all(color: bordeOffline),
            ),
            child: ElegirVariante(
              key: ValueKey(sel.productoId),
              producto: sel,
              disponible: widget.disponible,
              alAgregar: (v, n) => widget.alAgregar(sel, v, n),
            ),
          ),
      ],
    );
  }
}

/// `.mostrador-elegir`: talla y color, cantidad y "Agregar".
class ElegirVariante extends StatefulWidget {
  const ElegirVariante({super.key, required this.producto, required this.disponible, required this.alAgregar});
  final ProductoLocal producto;
  final int Function(ProductoLocal, VarianteLocal) disponible;
  final void Function(VarianteLocal, int) alAgregar;

  @override
  State<ElegirVariante> createState() => _ElegirVarianteState();
}

class _ElegirVarianteState extends State<ElegirVariante> {
  VarianteLocal? _variante;
  int _cantidad = 1;

  @override
  Widget build(BuildContext context) {
    final p = widget.producto;
    final v = _variante;
    final max = v == null ? 0 : widget.disponible(p, v);
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${p.nombre} · Bs ${bs(p.precio)}',
            style: textoOffline(peso: FontWeight.w700, color: marcaOffline),
          ),
          etiquetaOffline('Talla y color'),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final x in p.variantes)
                OpcionOffline(
                  texto: '${x.tallaCodigo} · ${x.colorNombre}',
                  sub: widget.disponible(p, x) < 1 ? 'sin stock' : 'quedan ${widget.disponible(p, x)}',
                  activa: identical(x, v),
                  onTap: widget.disponible(p, x) < 1
                      ? null
                      : () => setState(() {
                          _variante = x;
                          _cantidad = 1;
                        }),
                ),
            ],
          ),
          if (v != null) ...[
            etiquetaOffline('Cantidad'),
            Row(
              children: [
                IconButton.outlined(
                  onPressed: _cantidad > 1 ? () => setState(() => _cantidad--) : null,
                  icon: const Icon(Icons.remove, size: 18),
                ),
                SizedBox(
                  width: 40,
                  child: Text(
                    '$_cantidad',
                    textAlign: TextAlign.center,
                    style: textoOffline(size: 15, peso: FontWeight.w700),
                  ),
                ),
                IconButton.outlined(
                  onPressed: _cantidad < max ? () => setState(() => _cantidad++) : null,
                  icon: const Icon(Icons.add, size: 18),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: BotonOffline(
                    'Agregar · Bs ${bs(p.precio * _cantidad)}',
                    onPressed: _cantidad < 1 || _cantidad > max
                        ? null
                        : () {
                            widget.alAgregar(v, _cantidad);
                            setState(() {
                              _variante = null;
                              _cantidad = 1;
                            });
                          },
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// Lista de prendas elegidas (`.ventas-detalles--form`).
class LineasElegidas extends StatelessWidget {
  const LineasElegidas({super.key, required this.items, required this.alQuitar});
  final List<ItemLocal> items;
  final void Function(ItemLocal) alQuitar;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (final i in items)
        Container(
          padding: const EdgeInsets.symmetric(vertical: 6),
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE))),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(i.texto, style: textoOffline(size: 12.5)),
                    Text('Bs ${bs(i.precio * i.cantidad)}', style: textoOffline(size: 11.5, color: const Color(0xFF888888))),
                  ],
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                tooltip: 'Quitar',
                onPressed: () => alQuitar(i),
                icon: const Icon(Icons.close, size: 18),
              ),
            ],
          ),
        ),
    ],
  );
}

/// Lo que falta para registrar (`.ventas-falta`).
Widget faltaOffline(List<String> falta) => Padding(
  padding: const EdgeInsets.only(top: 10),
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [for (final f in falta) Text('• $f', style: textoOffline(size: 12, color: const Color(0xFFB3261E)))],
  ),
);

/// Tarjeta de una operacion del telefono (la tabla de la web, en celular).
class TarjetaOperacion extends StatelessWidget {
  const TarjetaOperacion({
    super.key,
    required this.titulo,
    required this.sub,
    required this.op,
    this.estadoTexto,
    this.extra = const [],
  });
  final String titulo;
  final String sub;
  final OperacionLocal op;
  final String? estadoTexto;
  final List<Widget> extra;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 8),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: Colors.white,
      border: Border.all(color: const Color(0xFFEEEEEE)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text(
                titulo,
                style: textoOffline(peso: FontWeight.w700, color: marcaOffline),
              ),
            ),
            const SizedBox(width: 8),
            ChipEstado(op.estado, texto: estadoTexto),
          ],
        ),
        subOffline(sub),
        const SizedBox(height: 6),
        for (final i in op.items) Text(i.texto, style: textoOffline(size: 12.5)),
        if (op.mensaje != null && op.mensaje!.isNotEmpty) subOffline(op.mensaje!),
        for (final n in op.noPagados)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              '${n.producto} (${n.talla}, ${n.color}) · ${n.motivo}',
              style: textoOffline(size: 12, color: const Color(0xFFB3261E)),
            ),
          ),
        ...extra,
      ],
    ),
  );
}

/// Fecha y hora con los selectores del sistema ("La recojo hasta").
class CampoFechaHora extends StatelessWidget {
  const CampoFechaHora({super.key, required this.etiqueta, required this.valor, required this.alCambiar});
  final String etiqueta;
  final DateTime valor;
  final ValueChanged<DateTime> alCambiar;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      etiquetaOffline(etiqueta),
      OutlinedButton.icon(
        style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder(), foregroundColor: marcaOffline),
        icon: const Icon(Icons.event, size: 18),
        label: Text(fechaCorta(valor)),
        onPressed: () async {
          final hoy = DateTime.now();
          final dia = await showDatePicker(
            context: context,
            initialDate: valor,
            firstDate: hoy,
            lastDate: hoy.add(const Duration(days: 60)),
          );
          if (dia == null || !context.mounted) return;
          final hora = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(valor));
          if (hora == null) return;
          alCambiar(DateTime(dia.year, dia.month, dia.day, hora.hour, hora.minute));
        },
      ),
    ],
  );
}

DateTime mananaMediodia() {
  final d = DateTime.now().add(const Duration(days: 1));
  return DateTime(d.year, d.month, d.day, 12);
}
