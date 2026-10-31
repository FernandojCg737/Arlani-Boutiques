import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';

import 'cuenta_repository.dart';
import 'estilo_cuenta.dart';

const _estado = {
  'solicitada': 'En revisión',
  'aprobada': 'Aprobada',
  'completada': 'Aprobada y reembolsada',
  'rechazada': 'Rechazada',
};
const _metodo = {
  'mismo_medio': 'al mismo medio de pago',
  'credito_tienda': 'como crédito en la tienda',
  'efectivo': 'en efectivo en la sucursal',
};
const _motivo = {
  'defecto': 'Defecto de fábrica',
  'talla_incorrecta': 'Talla incorrecta',
  'insatisfaccion': 'No cumplió expectativas',
  'otro': 'Otro motivo',
};

TonoEstado _tono(String estado) => switch (estado) {
      'completada' || 'aprobada' => TonoEstado.ok,
      'rechazada' => TonoEstado.mal,
      _ => TonoEstado.espera,
    };

/// "Mis devoluciones": las que pidio el cliente y en que van (como la web).
class MisDevoluciones extends ConsumerStatefulWidget {
  const MisDevoluciones({super.key});

  @override
  ConsumerState<MisDevoluciones> createState() => _MisDevolucionesState();
}

class _MisDevolucionesState extends ConsumerState<MisDevoluciones> {
  List<DevolucionCliente>? _devoluciones;

  @override
  void initState() {
    super.initState();
    ref.read(cuentaRepositoryProvider).devoluciones().then(
      (d) {
        if (mounted) setState(() => _devoluciones = d);
      },
      onError: (_) {
        if (mounted) setState(() => _devoluciones = []);
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final lista = _devoluciones;
    if (lista == null) return cargandoCuenta();
    if (lista.isEmpty) {
      return vacioCuenta('Todavía no tienes devoluciones. Desde Mis Compras puedes pedir una hasta 24 horas después de comprar.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final d in lista) ...[
          TarjetaCuenta(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text('Devolución #${d.id} · ${d.tiendaNombre}',
                          style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: tintaCuenta)),
                    ),
                    const SizedBox(width: 8),
                    InsigniaEstado(texto: _estado[d.estado] ?? d.estado, tono: _tono(d.estado)),
                  ],
                ),
                const SizedBox(height: 4),
                Text('Compra #${d.ventaId} · pedida el ${fechaLarga(d.fechaSolicitud)} · ${d.sucursalNombre}',
                    style: GoogleFonts.inter(fontSize: 12, height: 1.4, color: grisCuenta)),
                const SizedBox(height: 8),
                for (final linea in d.detalles)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(linea, style: GoogleFonts.inter(fontSize: 12.5, color: grisOscuroCuenta)),
                  ),
                const SizedBox(height: 6),
                Text.rich(
                  TextSpan(
                    text: '${_motivo[d.motivo] ?? d.motivo} · Reembolso de ',
                    children: [
                      TextSpan(text: 'Bs ${bs(d.montoReembolso)}', style: const TextStyle(fontWeight: FontWeight.w700, color: tintaCuenta)),
                      TextSpan(text: ' ${_metodo[d.metodoReembolso] ?? d.metodoReembolso}'),
                    ],
                  ),
                  style: GoogleFonts.inter(fontSize: 12.5, height: 1.4, color: grisOscuroCuenta),
                ),
                if (d.estado == 'rechazada' && (d.motivoRechazo ?? d.observaciones) != null) ...[
                  const SizedBox(height: 8),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    color: const Color(0xFFFDECEA),
                    child: Text('Motivo del rechazo: ${d.motivoRechazo ?? d.observaciones}',
                        style: GoogleFonts.inter(fontSize: 12.5, color: rojoCuenta)),
                  ),
                ],
                if (d.fechaResolucion != null) ...[
                  const SizedBox(height: 6),
                  Text('Resuelta el ${fechaCorta(d.fechaResolucion!)}', style: GoogleFonts.inter(fontSize: 11.5, color: grisCuenta)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}
