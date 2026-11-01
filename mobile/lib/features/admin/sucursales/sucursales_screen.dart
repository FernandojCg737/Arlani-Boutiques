import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme.dart';
import '../../../models/sucursal_admin.dart';
import '../admin_provider.dart';
import '../widgets/admin_widgets.dart';
import '../../../core/ubicacion.dart';

/// CU04 — Administrar Ciudades y Sucursales. Unica CU (junto a
/// temporadas/colecciones) que usa DELETE real; ademas usa el enum
/// activa/inactiva (no activo/inactivo).
class SucursalesScreen extends ConsumerStatefulWidget {
  const SucursalesScreen({super.key});

  @override
  ConsumerState<SucursalesScreen> createState() => _SucursalesScreenState();
}

class _SucursalesScreenState extends ConsumerState<SucursalesScreen> {
  late Future<List<SucursalAdmin>> _future;
  String? _error;

  @override
  void initState() {
    super.initState();
    _future = ref.read(adminRepositoryProvider).getSucursales();
  }

  void _reload() {
    setState(() {
      _error = null;
      _future = ref.read(adminRepositoryProvider).getSucursales();
    });
  }

  Future<void> _abrirFormulario({SucursalAdmin? sucursal}) async {
    final nombreCtrl = TextEditingController(text: sucursal?.nombre ?? '');
    final ciudadCtrl = TextEditingController(text: sucursal?.ciudadNombre ?? '');
    final departamentoCtrl = TextEditingController(text: sucursal?.departamento ?? '');
    final direccionCtrl = TextEditingController(text: sucursal?.direccion ?? '');
    final horarioCtrl = TextEditingController(text: sucursal?.horarioAtencion ?? '');
    final telefonoCtrl = TextEditingController(text: sucursal?.telefono ?? '');
    var estado = sucursal?.estado ?? 'activa';
    var latitud = sucursal?.latitud;
    var longitud = sucursal?.longitud;
    var ubicando = false;
    final formKey = GlobalKey<FormState>();

    await showAdminFormSheet(
      context,
      title: sucursal == null ? 'NUEVA SUCURSAL' : 'EDITAR SUCURSAL',
      builder: (context) => StatefulBuilder(
        builder: (context, setSheetState) => Form(
          key: formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextFormField(
                controller: nombreCtrl,
                decoration: const InputDecoration(labelText: 'Nombre de la sucursal'),
                validator: (v) => (v == null || v.trim().length < 2) ? 'Requerido' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: ciudadCtrl,
                decoration: const InputDecoration(labelText: 'Ciudad'),
                validator: (v) => (v == null || v.trim().length < 2) ? 'Requerido' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: departamentoCtrl,
                decoration: const InputDecoration(labelText: 'Departamento'),
                validator: (v) => (v == null || v.trim().length < 2) ? 'Requerido' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: direccionCtrl,
                decoration: const InputDecoration(labelText: 'Direccion'),
                validator: (v) => (v == null || v.trim().length < 3) ? 'Requerido' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(controller: horarioCtrl, decoration: const InputDecoration(labelText: 'Horario de atencion (opcional)')),
              const SizedBox(height: 16),
              TextFormField(controller: telefonoCtrl, decoration: const InputDecoration(labelText: 'Telefono (opcional)'), keyboardType: TextInputType.phone),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                initialValue: estado,
                decoration: const InputDecoration(labelText: 'Estado'),
                items: const [
                  DropdownMenuItem(value: 'activa', child: Text('Activa')),
                  DropdownMenuItem(value: 'inactiva', child: Text('Inactiva')),
                ],
                onChanged: (v) => setSheetState(() => estado = v!),
              ),
              const SizedBox(height: 16),
              Text(
                latitud != null && longitud != null
                    ? 'Ubicacion: ${latitud!.toStringAsFixed(5)}, ${longitud!.toStringAsFixed(5)}'
                    : 'Sin ubicacion cargada (CU01 no podra validar la asistencia de esta sucursal)',
                style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: ubicando
                    ? null
                    : () async {
                        setSheetState(() => ubicando = true);
                        try {
                          final pos = await ubicacionActual(
                            sinPermiso: 'Necesitamos permiso de ubicacion.',
                            gpsApagado: 'Activa el GPS del dispositivo.',
                          );
                          setSheetState(() {
                            latitud = pos.latitude;
                            longitud = pos.longitude;
                          });
                        } catch (_) {
                          // silencioso, el campo simplemente queda sin cargar
                        } finally {
                          setSheetState(() => ubicando = false);
                        }
                      },
                icon: const Icon(Icons.my_location, size: 16),
                label: Text(ubicando ? 'Obteniendo ubicacion...' : 'Usar mi ubicacion actual'),
              ),
              const SizedBox(height: 24),
              ElevatedButton(
                onPressed: () async {
                  if (!formKey.currentState!.validate()) return;
                  final repo = ref.read(adminRepositoryProvider);
                  try {
                    if (sucursal == null) {
                      await repo.createSucursal(
                        nombre: nombreCtrl.text.trim(),
                        ciudadNombre: ciudadCtrl.text.trim(),
                        departamento: departamentoCtrl.text.trim(),
                        direccion: direccionCtrl.text.trim(),
                        horarioAtencion: horarioCtrl.text.trim().isEmpty ? null : horarioCtrl.text.trim(),
                        telefono: telefonoCtrl.text.trim().isEmpty ? null : telefonoCtrl.text.trim(),
                        estado: estado,
                        latitud: latitud,
                        longitud: longitud,
                      );
                    } else {
                      await repo.updateSucursal(
                        id: sucursal.id,
                        nombre: nombreCtrl.text.trim(),
                        ciudadNombre: ciudadCtrl.text.trim(),
                        departamento: departamentoCtrl.text.trim(),
                        direccion: direccionCtrl.text.trim(),
                        horarioAtencion: horarioCtrl.text.trim().isEmpty ? null : horarioCtrl.text.trim(),
                        telefono: telefonoCtrl.text.trim().isEmpty ? null : telefonoCtrl.text.trim(),
                        estado: estado,
                        latitud: latitud,
                        longitud: longitud,
                      );
                    }
                    if (context.mounted) Navigator.pop(context);
                    _reload();
                  } catch (e) {
                    if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(_extractSucursalError(e))));
                  }
                },
                child: Text(sucursal == null ? 'CREAR SUCURSAL' : 'GUARDAR CAMBIOS'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _eliminar(SucursalAdmin sucursal) async {
    final ok = await confirmAdminAction(
      context,
      title: 'Eliminar sucursal',
      message: 'Seguro que queres eliminar ${sucursal.nombre}? Esta accion no se puede deshacer.',
    );
    if (!ok) return;
    try {
      await ref.read(adminRepositoryProvider).deleteSucursal(sucursal.id);
      _reload();
    } catch (e) {
      setState(() => _error = _extractSucursalError(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: 'SUCURSALES',
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _abrirFormulario(),
        icon: const Icon(Icons.add),
        label: const Text('NUEVA'),
      ),
      body: Column(
        children: [
          if (_error != null) AdminErrorBanner(message: _error!),
          Expanded(
            child: FutureBuilder<List<SucursalAdmin>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) return const Center(child: Text('No pudimos cargar las sucursales.'));
                final sucursales = snapshot.data ?? [];
                if (sucursales.isEmpty) return const Center(child: Text('No hay sucursales registradas.'));
                return ListView(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  children: [
                    for (final s in sucursales)
                      _SucursalCard(sucursal: s, onEditar: () => _abrirFormulario(sucursal: s), onEliminar: () => _eliminar(s)),
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

String _extractSucursalError(Object e) {
  final s = e.toString();
  return s.contains('No pudimos conectar') ? s : 'No pudimos completar la accion.';
}

class _SucursalCard extends StatelessWidget {
  const _SucursalCard({required this.sucursal, required this.onEditar, required this.onEliminar});

  final SucursalAdmin sucursal;
  final VoidCallback onEditar;
  final VoidCallback onEliminar;

  @override
  Widget build(BuildContext context) {
    final activa = sucursal.estado == 'activa';
    return AdminCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(sucursal.nombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
              ),
              EstadoBadge(estado: sucursal.estado, activo: activa),
            ],
          ),
          const SizedBox(height: 8),
          AdminInfoRow('Ciudad', '${sucursal.ciudadNombre} · ${sucursal.departamento}'),
          AdminInfoRow('Direccion', sucursal.direccion),
          AdminInfoRow('Horario', sucursal.horarioAtencion ?? '-'),
          AdminInfoRow('Telefono', sucursal.telefono ?? '-'),
          const SizedBox(height: 10),
          Row(
            children: [
              TextButton.icon(onPressed: onEditar, icon: const Icon(Icons.edit_outlined, size: 16), label: const Text('Editar')),
              TextButton.icon(
                onPressed: onEliminar,
                icon: const Icon(Icons.delete_outline, size: 16),
                label: const Text('Eliminar'),
                style: TextButton.styleFrom(foregroundColor: AppColors.danger),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
