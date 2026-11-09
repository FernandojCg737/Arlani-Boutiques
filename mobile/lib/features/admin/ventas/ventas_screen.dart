import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme.dart';
import '../../../models/venta_admin.dart';
import '../admin_provider.dart';
import '../widgets/admin_widgets.dart';

const _metodoLabel = {'paypal': 'PayPal / Tarjeta', 'qr': 'QR (transferencia)', 'efectivo': 'Efectivo en sucursal'};

/// CU11 "Gestion de Ventas" -- panel de solo lectura en mobile: ventas en
/// linea (PayPal/QR) y de mostrador en un solo lugar. Las acciones de
/// aprobar/rechazar QR y registrar venta presencial quedan en la web por
/// ahora (formularios largos, mas comodos en pantalla grande).
class VentasScreen extends ConsumerStatefulWidget {
  const VentasScreen({super.key});

  @override
  ConsumerState<VentasScreen> createState() => _VentasScreenState();
}

class _VentasScreenState extends ConsumerState<VentasScreen> {
  late Future<VentaAdminPage> _future;
  int _page = 1;
  String? _estadoPago;
  String? _error;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<VentaAdminPage> _load() {
    final repo = ref.read(adminRepositoryProvider);
    return repo.getVentas(page: _page, estadoPago: _estadoPago).catchError((Object e) {
      setState(() => _error = 'No pudimos cargar las ventas.');
      throw e;
    });
  }

  void _reload({int? page, String? estadoPago, bool clearEstado = false}) {
    setState(() {
      _error = null;
      if (page != null) _page = page;
      if (clearEstado) {
        _estadoPago = null;
        _page = 1;
      } else if (estadoPago != null) {
        _estadoPago = estadoPago;
        _page = 1;
      }
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: 'VENTAS',
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _FiltroChip(label: 'Todas', selected: _estadoPago == null, onTap: () => _reload(clearEstado: true)),
                  _FiltroChip(label: 'Completado', selected: _estadoPago == 'completado', onTap: () => _reload(estadoPago: 'completado')),
                  _FiltroChip(label: 'Verificando', selected: _estadoPago == 'verificando', onTap: () => _reload(estadoPago: 'verificando')),
                  _FiltroChip(label: 'Rechazado', selected: _estadoPago == 'rechazado', onTap: () => _reload(estadoPago: 'rechazado')),
                ],
              ),
            ),
          ),
          if (_error != null) AdminErrorBanner(message: _error!),
          Expanded(
            child: FutureBuilder<VentaAdminPage>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (!snapshot.hasData) {
                  return const Center(child: Text('No pudimos cargar las ventas.'));
                }
                final pagina = snapshot.data!;
                if (pagina.items.isEmpty) {
                  return const Center(child: Text('No hay ventas para estos filtros.'));
                }
                return ListView(
                  padding: const EdgeInsets.only(top: 8, bottom: 8),
                  children: [
                    for (final v in pagina.items) _VentaCard(venta: v),
                    _Paginador(page: pagina.page, totalPages: pagina.totalPages, onPageChange: (p) => _reload(page: p)),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _VentaCard extends StatelessWidget {
  const _VentaCard({required this.venta});
  final VentaAdmin venta;

  @override
  Widget build(BuildContext context) {
    return AdminCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(venta.clienteNombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                    Text(venta.clienteEmail, style: const TextStyle(fontSize: 11, color: AppColors.grayTextDark)),
                  ],
                ),
              ),
              Text('${venta.total.toStringAsFixed(2)} Bs', style: const TextStyle(fontWeight: FontWeight.w800, color: AppColors.brandDark)),
            ],
          ),
          const SizedBox(height: 8),
          AdminInfoRow('Venta', '#${venta.numero ?? venta.id} · ${venta.tipo == 'venta_digital' ? 'En linea' : 'Mostrador'}'),
          AdminInfoRow('Sucursal', venta.sucursalNombre),
          AdminInfoRow('Fecha', '${venta.fecha.day}/${venta.fecha.month}/${venta.fecha.year} ${venta.fecha.hour.toString().padLeft(2, '0')}:${venta.fecha.minute.toString().padLeft(2, '0')}'),
          if (venta.atendidoPorNombre != null) AdminInfoRow('Atendido por', venta.atendidoPorNombre!),
          const SizedBox(height: 6),
          Row(
            children: [
              NeutralBadge(_metodoLabel[venta.metodoPago] ?? venta.metodoPago),
              const SizedBox(width: 6),
              _EstadoPagoBadge(estado: venta.estadoPago),
            ],
          ),
        ],
      ),
    );
  }
}

class _EstadoPagoBadge extends StatelessWidget {
  const _EstadoPagoBadge({required this.estado});
  final String estado;

  @override
  Widget build(BuildContext context) {
    final color = switch (estado) {
      'completado' => AppColors.success,
      'rechazado' => AppColors.danger,
      _ => const Color(0xFFB26A00),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(border: Border.all(color: color)),
      child: Text(estado.toUpperCase(), style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: color, letterSpacing: 0.3)),
    );
  }
}

class _FiltroChip extends StatelessWidget {
  const _FiltroChip({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: ChoiceChip(label: Text(label), selected: selected, onSelected: (_) => onTap(), shape: const RoundedRectangleBorder()),
    );
  }
}

class _Paginador extends StatelessWidget {
  const _Paginador({required this.page, required this.totalPages, required this.onPageChange});
  final int page;
  final int totalPages;
  final ValueChanged<int> onPageChange;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          TextButton(onPressed: page > 1 ? () => onPageChange(page - 1) : null, child: const Text('Anterior')),
          Text('Pagina $page de $totalPages', style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
          TextButton(onPressed: page < totalPages ? () => onPageChange(page + 1) : null, child: const Text('Siguiente')),
        ],
      ),
    );
  }
}
