import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme.dart';
import '../../../models/bitacora_item.dart';
import '../admin_provider.dart';
import '../widgets/admin_widgets.dart';

const _meses = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
];

/// Formato compacto "3 sep de 2026, 4:05 p.m." sin depender de `intl`.
String _formatearFecha(DateTime fecha) {
  final local = fecha.toLocal();
  final hora12 = local.hour % 12 == 0 ? 12 : local.hour % 12;
  final ampm = local.hour < 12 ? 'a.m.' : 'p.m.';
  final minutos = local.minute.toString().padLeft(2, '0');
  return '${local.day} ${_meses[local.month - 1]} de ${local.year}, $hora12:$minutos $ampm';
}

/// CU17 — Auditar Operaciones (Bitacora). Lectura, paginada de a 20, con
/// busqueda por usuario/entidad — mismo criterio que `bitacora.ts`.
class BitacoraScreen extends ConsumerStatefulWidget {
  const BitacoraScreen({super.key});

  @override
  ConsumerState<BitacoraScreen> createState() => _BitacoraScreenState();
}

class _BitacoraScreenState extends ConsumerState<BitacoraScreen> {
  late Future<BitacoraPage> _future;
  int _page = 1;
  String? _buscar;
  String? _error;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<BitacoraPage> _load() {
    final repo = ref.read(adminRepositoryProvider);
    return repo.getBitacora(page: _page, buscar: _buscar).catchError((Object e) {
      setState(() => _error = 'No pudimos cargar la bitacora.');
      throw e;
    });
  }

  void _reload({int? page, String? buscar}) {
    setState(() {
      _error = null;
      if (page != null) _page = page;
      if (buscar != null) {
        _buscar = buscar.isEmpty ? null : buscar;
        _page = 1;
      }
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: 'BITACORA',
      body: Column(
        children: [
          AdminSearchField(hintText: 'Buscar por usuario o entidad...', onChanged: (v) => _reload(buscar: v)),
          if (_error != null) AdminErrorBanner(message: _error!),
          Expanded(
            child: FutureBuilder<BitacoraPage>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (!snapshot.hasData) {
                  return const Center(child: Text('No pudimos cargar la bitacora.'));
                }
                final pagina = snapshot.data!;
                if (pagina.items.isEmpty) {
                  return const Center(child: Text('No hay registros.'));
                }
                return ListView(
                  padding: const EdgeInsets.only(top: 8, bottom: 8),
                  children: [
                    for (final item in pagina.items) _BitacoraCard(item: item),
                    _Paginador(pagina: pagina, onPageChange: (p) => _reload(page: p)),
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

class _BitacoraCard extends StatelessWidget {
  const _BitacoraCard({required this.item});

  final BitacoraItem item;

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
                    Text(item.usuarioNombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                    Text(item.usuarioEmail, style: const TextStyle(fontSize: 11, color: AppColors.grayTextDark)),
                  ],
                ),
              ),
              NeutralBadge(item.accion),
            ],
          ),
          const SizedBox(height: 8),
          AdminInfoRow('Entidad', item.entidadId != null ? '${item.entidadAfectada} #${item.entidadNumero ?? item.entidadId}' : item.entidadAfectada),
          AdminInfoRow('Fecha', _formatearFecha(item.fecha)),
          AdminInfoRow('Dispositivo', item.plataforma == 'web' ? 'Web' : item.plataforma == 'movil' ? 'Movil' : '-'),
          AdminInfoRow('IP', item.ipAddress ?? '-'),
          if (item.detalle != null) AdminInfoRow('Detalle', item.detalle!),
        ],
      ),
    );
  }
}

class _Paginador extends StatelessWidget {
  const _Paginador({required this.pagina, required this.onPageChange});

  final BitacoraPage pagina;
  final ValueChanged<int> onPageChange;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          TextButton(
            onPressed: pagina.page > 1 ? () => onPageChange(pagina.page - 1) : null,
            child: const Text('Anterior'),
          ),
          Text('Pagina ${pagina.page} de ${pagina.totalPages}', style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
          TextButton(
            onPressed: pagina.page < pagina.totalPages ? () => onPageChange(pagina.page + 1) : null,
            child: const Text('Siguiente'),
          ),
        ],
      ),
    );
  }
}
