import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../../models/reserva_admin.dart';
import '../admin_provider.dart';
import '../widgets/admin_widgets.dart';

/// CU10 "Gestion de Reservas": cada reserva ya viene agrupada del backend
/// con TODOS sus productos en `detalles` -- si un cliente reservo varias
/// prendas juntas desde el carrito (`crearDesdeCarrito`), aca se ve como
/// una sola orden con la lista completa, no una fila por producto.
class ReservasScreen extends ConsumerStatefulWidget {
  const ReservasScreen({super.key});

  @override
  ConsumerState<ReservasScreen> createState() => _ReservasScreenState();
}

class _ReservasScreenState extends ConsumerState<ReservasScreen> {
  late Future<ReservaAdminPage> _future;
  int _page = 1;
  String? _estado;
  String? _error;
  int? _procesandoId;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<ReservaAdminPage> _load() {
    final repo = ref.read(adminRepositoryProvider);
    return repo.getReservas(page: _page, estado: _estado).catchError((Object e) {
      setState(() => _error = 'No pudimos cargar las reservas.');
      throw e;
    });
  }

  void _reload({int? page, String? estado, bool clearEstado = false}) {
    setState(() {
      _error = null;
      if (page != null) _page = page;
      if (clearEstado) {
        _estado = null;
        _page = 1;
      } else if (estado != null) {
        _estado = estado;
        _page = 1;
      }
      _future = _load();
    });
  }

  Future<void> _cambiarEstado(ReservaAdmin r, String estado) async {
    setState(() => _procesandoId = r.id);
    try {
      await ref.read(adminRepositoryProvider).cambiarEstadoReserva(r.id, estado);
      if (mounted) setState(() => _future = _load());
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(extractErrorMessage(e))));
      }
    } finally {
      if (mounted) setState(() => _procesandoId = null);
    }
  }

  Future<void> _completar(ReservaAdmin r) async {
    setState(() => _procesandoId = r.id);
    try {
      await ref.read(adminRepositoryProvider).completarReserva(r.id);
      if (mounted) setState(() => _future = _load());
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(extractErrorMessage(e))));
      }
    } finally {
      if (mounted) setState(() => _procesandoId = null);
    }
  }

  Future<void> _eliminar(ReservaAdmin r) async {
    final ok = await confirmAdminAction(
      context,
      title: 'Eliminar reserva',
      message: 'Se va a eliminar la reserva #${r.numero ?? r.id} de ${r.clienteNombre}. Esta accion no se puede deshacer.',
    );
    if (!ok) return;
    setState(() => _procesandoId = r.id);
    try {
      await ref.read(adminRepositoryProvider).eliminarReserva(r.id);
      if (mounted) setState(() => _future = _load());
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(extractErrorMessage(e))));
      }
    } finally {
      if (mounted) setState(() => _procesandoId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: 'RESERVAS',
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _FiltroChip(label: 'Todas', selected: _estado == null, onTap: () => _reload(clearEstado: true)),
                  _FiltroChip(label: 'Pendiente', selected: _estado == 'pendiente', onTap: () => _reload(estado: 'pendiente')),
                  _FiltroChip(label: 'Confirmada', selected: _estado == 'confirmada', onTap: () => _reload(estado: 'confirmada')),
                  _FiltroChip(label: 'Completada', selected: _estado == 'completada', onTap: () => _reload(estado: 'completada')),
                  _FiltroChip(label: 'Cancelada', selected: _estado == 'cancelada', onTap: () => _reload(estado: 'cancelada')),
                  _FiltroChip(label: 'Vencida', selected: _estado == 'vencida', onTap: () => _reload(estado: 'vencida')),
                ],
              ),
            ),
          ),
          if (_error != null) AdminErrorBanner(message: _error!),
          Expanded(
            child: FutureBuilder<ReservaAdminPage>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (!snapshot.hasData) {
                  return const Center(child: Text('No pudimos cargar las reservas.'));
                }
                final pagina = snapshot.data!;
                if (pagina.items.isEmpty) {
                  return const Center(child: Text('No hay reservas para estos filtros.'));
                }
                return ListView(
                  padding: const EdgeInsets.only(top: 8, bottom: 8),
                  children: [
                    for (final r in pagina.items)
                      _ReservaCard(
                        reserva: r,
                        procesando: _procesandoId == r.id,
                        onConfirmar: () => _cambiarEstado(r, 'confirmada'),
                        onCancelar: () => _cambiarEstado(r, 'cancelada'),
                        onCompletar: () => _completar(r),
                        onEliminar: () => _eliminar(r),
                      ),
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

class _ReservaCard extends StatelessWidget {
  const _ReservaCard({
    required this.reserva,
    required this.procesando,
    required this.onConfirmar,
    required this.onCancelar,
    required this.onCompletar,
    required this.onEliminar,
  });

  final ReservaAdmin reserva;
  final bool procesando;
  final VoidCallback onConfirmar;
  final VoidCallback onCancelar;
  final VoidCallback onCompletar;
  final VoidCallback onEliminar;

  @override
  Widget build(BuildContext context) {
    final totalItems = reserva.detalles.fold<int>(0, (sum, d) => sum + d.cantidad);
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
                    Text(reserva.clienteNombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                    Text(reserva.clienteEmail, style: const TextStyle(fontSize: 11, color: AppColors.grayTextDark)),
                  ],
                ),
              ),
              _EstadoBadge(estado: reserva.estado),
            ],
          ),
          const SizedBox(height: 8),
          AdminInfoRow('Reserva', '#${reserva.numero ?? reserva.id} · ${reserva.detalles.length} ${reserva.detalles.length == 1 ? 'producto' : 'productos'} ($totalItems u.)'),
          AdminInfoRow('Sucursal', reserva.sucursalNombre),
          AdminInfoRow(
            'Horario',
            '${reserva.horarioAtencion.day}/${reserva.horarioAtencion.month}/${reserva.horarioAtencion.year} '
                '${reserva.horarioAtencion.hour.toString().padLeft(2, '0')}:${reserva.horarioAtencion.minute.toString().padLeft(2, '0')}',
          ),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: const BoxDecoration(color: Color(0xFFF7F7F5)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final d in reserva.detalles)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(
                      '${d.cantidad}x ${d.productoNombre} (${d.tallaCodigo}, ${d.colorNombre})',
                      style: const TextStyle(fontSize: 12, color: AppColors.brandDark),
                    ),
                  ),
              ],
            ),
          ),
          if (reserva.activa) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (reserva.estado == 'pendiente')
                  OutlinedButton(
                    onPressed: procesando ? null : onConfirmar,
                    style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder(), padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6)),
                    child: const Text('CONFIRMAR', style: TextStyle(fontSize: 11)),
                  ),
                OutlinedButton(
                  onPressed: procesando ? null : onCompletar,
                  style: OutlinedButton.styleFrom(
                    shape: const RoundedRectangleBorder(),
                    foregroundColor: AppColors.success,
                    side: const BorderSide(color: AppColors.success),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  ),
                  child: const Text('COBRAR Y ENTREGAR', style: TextStyle(fontSize: 11)),
                ),
                OutlinedButton(
                  onPressed: procesando ? null : onCancelar,
                  style: OutlinedButton.styleFrom(
                    shape: const RoundedRectangleBorder(),
                    foregroundColor: AppColors.danger,
                    side: const BorderSide(color: Color(0xFFF3C9C5)),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  ),
                  child: const Text('CANCELAR', style: TextStyle(fontSize: 11)),
                ),
              ],
            ),
          ],
          Align(
            alignment: Alignment.centerRight,
            child: IconButton(
              onPressed: procesando ? null : onEliminar,
              icon: const Icon(Icons.delete_outline, size: 18, color: AppColors.grayText),
              tooltip: 'Eliminar reserva',
            ),
          ),
        ],
      ),
    );
  }
}

class _EstadoBadge extends StatelessWidget {
  const _EstadoBadge({required this.estado});
  final String estado;

  @override
  Widget build(BuildContext context) {
    final color = switch (estado) {
      'completada' => AppColors.success,
      'confirmada' => AppColors.brandDark,
      'cancelada' || 'vencida' => AppColors.danger,
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
