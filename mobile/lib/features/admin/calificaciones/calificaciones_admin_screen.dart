import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme.dart';
import '../../../models/calificacion_admin.dart';
import '../admin_provider.dart';
import '../widgets/admin_widgets.dart';

/// CU20 "Reputacion y Calificaciones" -- promedio general (sobre TODAS las
/// calificaciones, sin importar el filtro de la tabla), desglose por
/// estrellas y el detalle de quien califico que compra.
class CalificacionesAdminScreen extends ConsumerStatefulWidget {
  const CalificacionesAdminScreen({super.key});

  @override
  ConsumerState<CalificacionesAdminScreen> createState() => _CalificacionesAdminScreenState();
}

class _CalificacionesAdminScreenState extends ConsumerState<CalificacionesAdminScreen> {
  late Future<CalificacionPage> _future;
  int _page = 1;
  int? _estrellas;
  String? _error;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<CalificacionPage> _load() {
    final repo = ref.read(adminRepositoryProvider);
    return repo.getCalificaciones(page: _page, estrellas: _estrellas).catchError((Object e) {
      setState(() => _error = 'No pudimos cargar las calificaciones.');
      throw e;
    });
  }

  void _reload({int? page, int? estrellas, bool clearEstrellas = false}) {
    setState(() {
      _error = null;
      if (page != null) _page = page;
      if (clearEstrellas) {
        _estrellas = null;
        _page = 1;
      } else if (estrellas != null) {
        _estrellas = estrellas;
        _page = 1;
      }
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: 'CALIFICACIONES',
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _FiltroChip(label: 'Todas', selected: _estrellas == null, onTap: () => _reload(clearEstrellas: true)),
                  for (final n in [5, 4, 3, 2, 1])
                    _FiltroChip(label: '$n★', selected: _estrellas == n, onTap: () => _reload(estrellas: n)),
                ],
              ),
            ),
          ),
          if (_error != null) AdminErrorBanner(message: _error!),
          Expanded(
            child: FutureBuilder<CalificacionPage>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (!snapshot.hasData) {
                  return const Center(child: Text('No pudimos cargar las calificaciones.'));
                }
                final pagina = snapshot.data!;
                return ListView(
                  padding: const EdgeInsets.only(top: 8, bottom: 8),
                  children: [
                    _ResumenBox(resumen: pagina.resumen),
                    if (pagina.items.isEmpty)
                      const Padding(
                        padding: EdgeInsets.all(24),
                        child: Center(child: Text('No hay calificaciones para estos filtros.')),
                      )
                    else ...[
                      for (final c in pagina.items) _CalificacionCard(calificacion: c),
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            TextButton(onPressed: pagina.page > 1 ? () => _reload(page: pagina.page - 1) : null, child: const Text('Anterior')),
                            Text('Pagina ${pagina.page} de ${pagina.totalPages}', style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                            TextButton(onPressed: pagina.page < pagina.totalPages ? () => _reload(page: pagina.page + 1) : null, child: const Text('Siguiente')),
                          ],
                        ),
                      ),
                    ],
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

class _ResumenBox extends StatelessWidget {
  const _ResumenBox({required this.resumen});
  final CalificacionResumen resumen;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
      child: Column(
        children: [
          Text(resumen.promedio.toStringAsFixed(1), style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w800, color: AppColors.brandDark)),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(
              5,
              (i) => Icon(i < resumen.promedio.round() ? Icons.star : Icons.star_border, size: 16, color: const Color(0xFFE8B923)),
            ),
          ),
          Text('${resumen.total} calificaciones', style: const TextStyle(fontSize: 11, color: AppColors.grayText, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

class _CalificacionCard extends StatelessWidget {
  const _CalificacionCard({required this.calificacion});
  final CalificacionAdmin calificacion;

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
                    Text(calificacion.clienteNombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                    Text(calificacion.clienteEmail, style: const TextStyle(fontSize: 11, color: AppColors.grayTextDark)),
                  ],
                ),
              ),
              Row(
                children: List.generate(
                  5,
                  (i) => Icon(i < calificacion.estrellas ? Icons.star : Icons.star_border, size: 14, color: const Color(0xFFE8B923)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          AdminInfoRow('Venta', '#${calificacion.ventaNumero ?? calificacion.ventaId} · ${calificacion.sucursalNombre}'),
          if (calificacion.empleadoNombre != null) AdminInfoRow('Atendido por', calificacion.empleadoNombre!),
          if (calificacion.comentario != null && calificacion.comentario!.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text('"${calificacion.comentario}"', style: const TextStyle(fontSize: 12, fontStyle: FontStyle.italic, color: AppColors.grayTextDark)),
          ],
        ],
      ),
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
