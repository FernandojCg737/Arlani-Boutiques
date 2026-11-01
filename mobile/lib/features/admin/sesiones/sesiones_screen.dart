import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/api_client.dart';
import '../../../core/theme.dart';
import '../../../models/asistencia.dart';
import '../../../models/usuario.dart';
import '../../auth/auth_provider.dart';
import '../admin_provider.dart';
import '../widgets/admin_widgets.dart';
import 'asistencia_provider.dart';
import '../../../core/ubicacion.dart';

const _diasSemana = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo'];

/// Bolivia no tiene horario de verano: UTC-4 fijo todo el año. Se resta a
/// mano en vez de usar timezone local del dispositivo, para que la hora
/// mostrada sea correcta sin importar en que zona horaria este el celular.
DateTime _bolivia(DateTime utc) => utc.toUtc().add(const Duration(hours: -4));

String _horaBolivia(DateTime utc) {
  final b = _bolivia(utc);
  final h12 = b.hour % 12 == 0 ? 12 : b.hour % 12;
  final ampm = b.hour < 12 ? 'a.m.' : 'p.m.';
  return '$h12:${b.minute.toString().padLeft(2, '0')} $ampm';
}

/// CU01 — Gestionar Inicio y Cierre de Sesion, con el agregado de Control de
/// Asistencia (clave diaria de 5 minutos + foto + ubicacion validada contra
/// la sucursal): el Administrador configura/libera la clave y ve quien
/// marco (o quien quedo con falta); Encargado/Cajero la ingresan para
/// marcar la suya, con su historial semanal Lunes-Domingo.
class SesionesScreen extends ConsumerStatefulWidget {
  const SesionesScreen({super.key});

  @override
  ConsumerState<SesionesScreen> createState() => _SesionesScreenState();
}

class _SesionesScreenState extends ConsumerState<SesionesScreen> {
  EstadoAsistencia? _estado;
  List<MarcadoHoy> _marcadosHoy = [];
  List<Marcado> _historial = [];
  List<Marcado> _miHistorial = [];
  bool _cargandoAsistencia = false;
  bool _guardandoHora = false;
  bool _liberando = false;
  bool _marcando = false;
  String _mensaje = '';
  String _errorMensaje = '';
  final _codigoCtrl = TextEditingController();
  TimeOfDay? _horaSeleccionada;
  XFile? _foto;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _cargarAsistencia());
    // Refresca el estado (cuenta la ventana de 5 min) cada 10s.
    _pollTimer = Timer.periodic(const Duration(seconds: 10), (_) => _cargarEstadoSolo());
  }

  @override
  void dispose() {
    _codigoCtrl.dispose();
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _cargarEstadoSolo() async {
    try {
      final estado = await ref.read(asistenciaRepositoryProvider).estado();
      if (mounted) setState(() => _estado = estado);
    } catch (_) {
      // silencioso
    }
  }

  Future<void> _cargarAsistencia() async {
    setState(() => _cargandoAsistencia = true);
    final repo = ref.read(asistenciaRepositoryProvider);
    final esAdmin = ref.read(authProvider).usuario?.isAdministrador ?? false;
    try {
      final estado = await repo.estado();
      if (!mounted) return;
      setState(() {
        _estado = estado;
        final partes = estado.horaLiberacion.split(':');
        _horaSeleccionada = TimeOfDay(hour: int.parse(partes[0]), minute: int.parse(partes[1]));
      });
      if (esAdmin) {
        final hoy = await repo.marcadosHoy();
        final hist = await repo.historial();
        if (!mounted) return;
        setState(() {
          _marcadosHoy = hoy;
          _historial = hist;
        });
      } else {
        final mio = await repo.miHistorial();
        if (!mounted) return;
        setState(() => _miHistorial = mio);
      }
    } catch (_) {
      // silencioso, igual que la web
    } finally {
      if (mounted) setState(() => _cargandoAsistencia = false);
    }
  }

  Future<void> _guardarHora() async {
    if (_horaSeleccionada == null) return;
    setState(() => _guardandoHora = true);
    try {
      final hh = _horaSeleccionada!.hour.toString().padLeft(2, '0');
      final mm = _horaSeleccionada!.minute.toString().padLeft(2, '0');
      final estado = await ref.read(asistenciaRepositoryProvider).configurarHora('$hh:$mm');
      setState(() {
        _estado = estado;
        _mensaje = 'Hora de liberacion actualizada.';
      });
    } catch (e) {
      setState(() => _errorMensaje = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _guardandoHora = false);
    }
  }

  Future<void> _liberarAhora() async {
    setState(() => _liberando = true);
    try {
      final estado = await ref.read(asistenciaRepositoryProvider).liberarManual();
      setState(() {
        _estado = estado;
        _mensaje = 'Clave liberada por 5 minutos.';
      });
      final hoy = await ref.read(asistenciaRepositoryProvider).marcadosHoy();
      if (mounted) setState(() => _marcadosHoy = hoy);
    } catch (e) {
      setState(() => _errorMensaje = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _liberando = false);
    }
  }

  Future<void> _tomarFoto() async {
    final foto = await ImagePicker().pickImage(source: ImageSource.camera, imageQuality: 85, preferredCameraDevice: CameraDevice.front);
    if (foto != null && mounted) setState(() => _foto = foto);
  }

  Future<void> _marcarAsistencia() async {
    if (_foto == null) {
      setState(() => _errorMensaje = 'Toma una foto de verificacion antes de marcar.');
      return;
    }
    setState(() {
      _marcando = true;
      _mensaje = '';
      _errorMensaje = '';
    });
    try {
      final pos = await ubicacionActual(
        sinPermiso: 'Necesitamos permiso de ubicacion para marcar tu asistencia.',
        gpsApagado: 'Activa la ubicacion (GPS) de tu dispositivo para marcar asistencia.',
      );

      await ref.read(asistenciaRepositoryProvider).marcar(
            codigo: _codigoCtrl.text.trim(),
            latitud: pos.latitude,
            longitud: pos.longitude,
            fotoPath: _foto!.path,
          );

      _codigoCtrl.clear();
      setState(() {
        _mensaje = 'Asistencia marcada correctamente.';
        _foto = null;
      });
      final mio = await ref.read(asistenciaRepositoryProvider).miHistorial();
      if (mounted) setState(() => _miHistorial = mio);
    } catch (e) {
      setState(() => _errorMensaje = e is String ? e : extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _marcando = false);
    }
  }

  List<({String dia, Marcado? marcado})> _filaSemanaActual() {
    final hoy = _bolivia(DateTime.now().toUtc());
    final diaIso = hoy.weekday - 1; // 0=lunes ... 6=domingo
    final lunes = DateTime(hoy.year, hoy.month, hoy.day).subtract(Duration(days: diaIso));
    final porFecha = {for (final m in _miHistorial) m.fecha: m};

    return List.generate(7, (i) {
      final fecha = lunes.add(Duration(days: i));
      final iso =
          '${fecha.year.toString().padLeft(4, '0')}-${fecha.month.toString().padLeft(2, '0')}-${fecha.day.toString().padLeft(2, '0')}';
      return (dia: _diasSemana[i], marcado: porFecha[iso]);
    });
  }

  @override
  Widget build(BuildContext context) {
    final sesionesAsync = ref.watch(sesionesActivasProvider);
    final esAdmin = ref.watch(authProvider).usuario?.isAdministrador ?? false;

    return AdminScaffold(
      title: 'SESIONES ACTIVAS',
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(sesionesActivasProvider);
          await _cargarAsistencia();
        },
        child: ListView(
          padding: const EdgeInsets.fromLTRB(0, 16, 0, 32),
          children: [
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                'Cada login reemplaza la sesion anterior (una sola sesion por cuenta) y expira sola a los 60 minutos.',
                style: TextStyle(fontSize: 12, color: AppColors.grayTextDark, fontStyle: FontStyle.italic),
              ),
            ),
            const SizedBox(height: 16),
            sesionesAsync.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (err, _) => const Padding(
                padding: EdgeInsets.symmetric(horizontal: 16),
                child: AdminErrorBanner(message: 'No pudimos cargar las sesiones activas.'),
              ),
              data: (sesiones) => sesiones.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 16),
                      child: Text('No hay sesiones activas.'),
                    )
                  : Column(children: [for (final u in sesiones) _SesionCard(usuario: u)]),
            ),
            const Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Divider(height: 48)),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                'CONTROL DE ASISTENCIA',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: AppColors.brandDark),
              ),
            ),
            const SizedBox(height: 12),
            if (_cargandoAsistencia && _estado == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              )
            else ...[
              if (_mensaje.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                  child: Text(_mensaje, style: const TextStyle(fontSize: 12, color: AppColors.success)),
                ),
              if (_errorMensaje.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                  child: Text(_errorMensaje, style: const TextStyle(fontSize: 12, color: AppColors.danger)),
                ),
              if (esAdmin) _buildAdmin() else _buildStaff(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildAdmin() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        AdminCard(
          child: Row(
            children: [
              Expanded(
                child: Row(
                  children: [
                    const Text('Hora de liberacion (Bolivia):', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                    const SizedBox(width: 8),
                    TextButton(
                      onPressed: () async {
                        final elegida = await showTimePicker(
                          context: context,
                          initialTime: _horaSeleccionada ?? const TimeOfDay(hour: 8, minute: 0),
                        );
                        if (elegida != null) setState(() => _horaSeleccionada = elegida);
                      },
                      child: Text(_horaSeleccionada?.format(context) ?? '--:--'),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: _guardandoHora ? null : _guardarHora,
                child: Text(_guardandoHora ? '...' : 'GUARDAR'),
              ),
            ],
          ),
        ),
        AdminCard(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              EstadoBadge(
                estado: _estado?.liberado == true
                    ? 'liberada (5 min)'
                    : _estado?.ventanaCerrada == true
                        ? 'ventana cerrada'
                        : 'no liberada',
                activo: _estado?.liberado == true,
              ),
              if (_estado?.codigo != null)
                Text(
                  _estado!.codigo!,
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppColors.brandDark, letterSpacing: 2),
                ),
              if (_estado?.liberado == false)
                ElevatedButton(
                  onPressed: _liberando ? null : _liberarAhora,
                  child: Text(_liberando ? '...' : 'LIBERAR AHORA'),
                ),
            ],
          ),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text('QUIEN MARCO HOY', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: AppColors.brandDark)),
        ),
        if (_marcadosHoy.isEmpty)
          const Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Text('Sin personal activo registrado.'))
        else
          for (final m in _marcadosHoy)
            AdminCard(
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(m.empleadoNombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                        if (m.sucursalNombre != null)
                          Text(m.sucursalNombre!, style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                      ],
                    ),
                  ),
                  EstadoBadge(
                    estado: m.estado == 'marco' ? 'marco' : m.estado == 'falta' ? 'falta' : 'pendiente',
                    activo: m.estado == 'marco',
                  ),
                ],
              ),
            ),
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text('HISTORIAL (ULTIMOS 7 DIAS)', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: AppColors.brandDark)),
        ),
        if (_historial.isEmpty)
          const Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Text('Sin marcados en el rango.'))
        else
          for (final h in _historial)
            AdminCard(
              child: Row(
                children: [
                  if (h.fotoUrl != null) ...[
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: Image.network(h.fotoUrl!, width: 44, height: 44, fit: BoxFit.cover),
                    ),
                    const SizedBox(width: 12),
                  ],
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(h.empleadoNombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                        Text(
                          '${h.sucursalNombre ?? '-'} · ${h.fecha} · ${_horaBolivia(h.horaMarcado)}',
                          style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
      ],
    );
  }

  Widget _buildStaff() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_estado?.ventanaCerrada == true)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              'La ventana de 5 minutos de hoy ya se cerro. Si no marcaste, quedaste registrado como falta.',
              style: TextStyle(fontSize: 13, color: AppColors.danger),
            ),
          )
        else if (_estado?.liberado == false)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              'La clave todavia no fue liberada (se libera a las ${_estado!.horaLiberacion} hora Bolivia, o antes si tu Administrador la libera manualmente). Solo dura 5 minutos.',
              style: const TextStyle(fontSize: 13, color: AppColors.grayTextDark),
            ),
          )
        else if (_estado?.liberado == true)
          AdminCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('CLAVE DEL DIA (5 MINUTOS)', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.grayTextDark)),
                const SizedBox(height: 8),
                TextField(
                  controller: _codigoCtrl,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 22, letterSpacing: 4, fontWeight: FontWeight.w800),
                  decoration: const InputDecoration(counterText: '', hintText: '000000'),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _tomarFoto,
                        icon: const Icon(Icons.camera_alt_outlined, size: 18),
                        label: Text(_foto == null ? 'TOMAR FOTO' : 'FOTO LISTA'),
                      ),
                    ),
                    if (_foto != null) ...[
                      const SizedBox(width: 12),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: Image.file(File(_foto!.path), width: 48, height: 48, fit: BoxFit.cover),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 8),
                ElevatedButton(
                  onPressed: _marcando || _codigoCtrl.text.trim().isEmpty || _foto == null ? null : _marcarAsistencia,
                  child: Text(_marcando ? 'MARCANDO...' : 'MARCAR ASISTENCIA'),
                ),
              ],
            ),
          ),
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text('MI HISTORIAL (SEMANA ACTUAL)', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: AppColors.brandDark)),
        ),
        for (final f in _filaSemanaActual())
          AdminCard(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(f.dia, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                if (f.marcado != null) Text(_horaBolivia(f.marcado!.horaMarcado), style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                EstadoBadge(estado: f.marcado != null ? 'marcado' : 'sin marcar', activo: f.marcado != null),
              ],
            ),
          ),
      ],
    );
  }
}

class _SesionCard extends StatelessWidget {
  const _SesionCard({required this.usuario});

  final Usuario usuario;

  @override
  Widget build(BuildContext context) {
    return AdminCard(
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(usuario.nombre, style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandDark)),
                Text(usuario.email, style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              NeutralBadge(usuario.tipo.replaceAll('_', ' ')),
              if (usuario.rol != null) ...[
                const SizedBox(height: 4),
                Text(usuario.rol!, style: const TextStyle(fontSize: 11, color: AppColors.grayText)),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
