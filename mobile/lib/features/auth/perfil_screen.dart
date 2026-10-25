import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme.dart';
import '../../models/notificacion.dart';
import '../../models/reserva.dart';
import '../../models/usuario.dart';
import '../../models/venta.dart';
import '../../widgets/password_strength.dart';
import '../notificaciones/notificaciones_provider.dart';
import '../storefront/reservas_repository.dart';
import '../storefront/ventas_repository.dart';
import 'auth_provider.dart';

enum _Tab { resumen, reservas, compras, pagos, notificaciones, datos, seguridad }

const _metodoLabel = {'paypal': 'PayPal / Tarjeta', 'qr': 'QR (transferencia)', 'efectivo': 'Efectivo en sucursal'};

/// "Mi Cuenta": para clientes, replica exacto el dashboard con tabs de
/// `perfil.ts`/`perfil.html` en la web (Resumen/Mis Reservas/Mis Compras/
/// Metodos de Pago/Notificaciones/Mis Datos/Seguridad). Para staff (sin
/// reservas/compras propias) se mantiene la version simple de solo
/// Datos personales + Cambiar contrasena, igual que la rama no-cliente
/// de esa misma pagina en la web.
class PerfilScreen extends ConsumerStatefulWidget {
  const PerfilScreen({super.key});

  @override
  ConsumerState<PerfilScreen> createState() => _PerfilScreenState();
}

class _PerfilScreenState extends ConsumerState<PerfilScreen> {
  _Tab _tab = _Tab.resumen;

  List<Reserva>? _reservas;
  List<Venta>? _compras;
  bool _cargandoReservas = true;
  bool _cargandoCompras = true;
  int? _procesandoReservaId;

  int? _calificandoVentaId;
  int _estrellas = 0;
  final _comentarioCtrl = TextEditingController();
  bool _guardandoCalificacion = false;
  String? _errorCalificacion;

  late final TextEditingController _nombreCtrl;
  late final TextEditingController _telefonoCtrl;
  late final TextEditingController _direccionCtrl;
  bool _savingPerfil = false;
  String? _errorPerfil;
  String? _successPerfil;

  final _actualCtrl = TextEditingController();
  final _nuevaCtrl = TextEditingController();
  bool _savingPassword = false;
  String? _errorPassword;
  String? _successPassword;

  @override
  void initState() {
    super.initState();
    final usuario = ref.read(authProvider).usuario;
    _nombreCtrl = TextEditingController(text: usuario?.nombre ?? '');
    _telefonoCtrl = TextEditingController(text: usuario?.telefono ?? '');
    _direccionCtrl = TextEditingController(text: usuario?.direccion ?? '');
    if (usuario?.isCliente ?? false) {
      _cargarReservas();
      _cargarCompras();
      ref.read(notificacionesProvider.notifier).cargar();
    }
  }

  @override
  void dispose() {
    _nombreCtrl.dispose();
    _telefonoCtrl.dispose();
    _direccionCtrl.dispose();
    _actualCtrl.dispose();
    _nuevaCtrl.dispose();
    _comentarioCtrl.dispose();
    super.dispose();
  }

  Future<void> _cargarReservas() async {
    setState(() => _cargandoReservas = true);
    try {
      final r = await ref.read(reservasRepositoryProvider).misReservas();
      if (mounted) setState(() => _reservas = r);
    } catch (_) {
      if (mounted) setState(() => _reservas = []);
    } finally {
      if (mounted) setState(() => _cargandoReservas = false);
    }
  }

  Future<void> _cargarCompras() async {
    setState(() => _cargandoCompras = true);
    try {
      final c = await ref.read(ventasRepositoryProvider).misCompras();
      if (mounted) setState(() => _compras = c);
    } catch (_) {
      if (mounted) setState(() => _compras = []);
    } finally {
      if (mounted) setState(() => _cargandoCompras = false);
    }
  }

  Future<void> _cancelarReserva(Reserva r) async {
    setState(() => _procesandoReservaId = r.id);
    try {
      await ref.read(reservasRepositoryProvider).cancelar(r.id);
      await _cargarReservas();
    } catch (_) {
      // Igual que la web: si falla, la reserva simplemente no cambia de estado.
    } finally {
      if (mounted) setState(() => _procesandoReservaId = null);
    }
  }

  void _abrirCalificar(Venta v) {
    setState(() {
      _calificandoVentaId = v.id;
      _estrellas = 0;
      _comentarioCtrl.clear();
      _errorCalificacion = null;
    });
  }

  void _abrirSolicitarDevolucion(Venta v) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _SolicitarDevolucionSheet(
        venta: v,
        onSuccess: _cargarCompras,
      ),
    );
  }

  Future<void> _enviarCalificacion(Venta v) async {
    if (_estrellas < 1) return;
    setState(() {
      _guardandoCalificacion = true;
      _errorCalificacion = null;
    });
    try {
      await ref.read(ventasRepositoryProvider).calificar(
            ventaId: v.id,
            estrellas: _estrellas,
            comentario: _comentarioCtrl.text.trim().isEmpty ? null : _comentarioCtrl.text.trim(),
          );
      if (!mounted) return;
      setState(() => _calificandoVentaId = null);
      await _cargarCompras();
    } catch (e) {
      if (mounted) setState(() => _errorCalificacion = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _guardandoCalificacion = false);
    }
  }

  Future<void> _guardarPerfil() async {
    setState(() {
      _savingPerfil = true;
      _errorPerfil = null;
      _successPerfil = null;
    });
    try {
      await ref.read(authProvider.notifier).updateProfile(
            nombre: _nombreCtrl.text.trim(),
            telefono: _telefonoCtrl.text.trim().isEmpty ? null : _telefonoCtrl.text.trim(),
            direccion: _direccionCtrl.text.trim().isEmpty ? null : _direccionCtrl.text.trim(),
          );
      if (mounted) setState(() => _successPerfil = 'Tus datos se actualizaron correctamente.');
    } catch (e) {
      if (mounted) setState(() => _errorPerfil = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _savingPerfil = false);
    }
  }

  Future<void> _cambiarPassword() async {
    if (!isPasswordValid(_nuevaCtrl.text)) {
      setState(() => _errorPassword = 'La nueva contrasena no cumple los requisitos.');
      return;
    }
    setState(() {
      _savingPassword = true;
      _errorPassword = null;
      _successPassword = null;
    });
    try {
      await ref.read(authProvider.notifier).changePassword(actual: _actualCtrl.text, nueva: _nuevaCtrl.text);
      _actualCtrl.clear();
      _nuevaCtrl.clear();
      if (mounted) setState(() => _successPassword = 'Tu contrasena se actualizo.');
    } catch (e) {
      if (mounted) setState(() => _errorPassword = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _savingPassword = false);
    }
  }

  int get _reservasActivas => (_reservas ?? []).where((r) => r.estado == 'pendiente' || r.estado == 'confirmada').length;

  double get _totalGastado =>
      (_compras ?? []).where((v) => v.estadoPago == 'completado').fold(0.0, (sum, v) => sum + v.total);

  List<MapEntry<String, int>> get _metodosUsados {
    final conteo = <String, int>{};
    for (final v in _compras ?? <Venta>[]) {
      if (v.estadoPago != 'completado') continue;
      conteo[v.metodoPago] = (conteo[v.metodoPago] ?? 0) + 1;
    }
    return conteo.entries.toList();
  }

  @override
  Widget build(BuildContext context) {
    final usuario = ref.watch(authProvider).usuario;
    final isCliente = usuario?.isCliente ?? false;

    return Scaffold(
      appBar: AppBar(
        title: Text(isCliente ? 'MI CUENTA' : 'MI PERFIL'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Cerrar sesion',
            onPressed: () async {
              await ref.read(authProvider.notifier).logout();
              if (context.mounted) context.go('/');
            },
          ),
        ],
      ),
      body: SafeArea(
        child: isCliente ? _buildDashboard(usuario!) : _buildStaff(usuario),
      ),
    );
  }

  // ---------------------------------------------------------- Dashboard cliente

  Widget _buildDashboard(Usuario usuario) {
    final noLeidas = ref.watch(notificacionesNoLeidasProvider);
    final auth = ref.watch(authProvider);
    final visibleTabs = <_Tab>[
      _Tab.resumen,
      if (auth.hasPermiso('CU10')) _Tab.reservas,
      if (auth.hasPermiso('CU11')) ...[_Tab.compras, _Tab.pagos],
      if (auth.hasPermiso('CU14')) _Tab.notificaciones,
      if (auth.hasPermiso('CU15')) ...[_Tab.datos, _Tab.seguridad],
    ];
    if (!visibleTabs.contains(_tab)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => _tab = _Tab.resumen);
      });
    }

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: Row(
            children: [
              TextButton.icon(
                onPressed: () => context.go('/'),
                icon: const Icon(Icons.arrow_back, size: 16),
                label: const Text('VOLVER AL INICIO'),
                style: TextButton.styleFrom(foregroundColor: AppColors.brandDark, padding: EdgeInsets.zero),
              ),
              const Spacer(),
              if (auth.hasPermiso('CU13'))
                OutlinedButton.icon(
                  onPressed: () => context.push('/carrito'),
                  icon: const Icon(Icons.shopping_bag_outlined, size: 16),
                  label: const Text('MI CARRITO'),
                  style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder(), padding: const EdgeInsets.symmetric(horizontal: 12)),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'HOLA, ${usuario.nombre.toUpperCase()}',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: AppColors.brandDark),
            ),
          ),
        ),
        _TabsBar(
          tab: _tab,
          noLeidas: noLeidas,
          visibleTabs: visibleTabs,
          onSelect: (t) => setState(() => _tab = t),
        ),
        Expanded(
          child: switch (_tab) {
            _Tab.resumen => _buildResumen(),
            _Tab.reservas => _buildReservas(),
            _Tab.compras => _buildCompras(),
            _Tab.pagos => _buildPagos(),
            _Tab.notificaciones => _buildNotificaciones(),
            _Tab.datos => _buildDatos(usuario),
            _Tab.seguridad => _buildSeguridad(),
          },
        ),
      ],
    );
  }

  Widget _buildResumen() {
    final auth = ref.watch(authProvider);
    final verReservas = auth.hasPermiso('CU10');
    final verCompras = auth.hasPermiso('CU11');
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
      children: [
        if (verReservas || verCompras)
          Row(
            children: [
              if (verReservas) Expanded(child: _StatCard(label: 'Reservas activas', value: '$_reservasActivas')),
              if (verReservas && verCompras) const SizedBox(width: 10),
              if (verCompras) Expanded(child: _StatCard(label: 'Compras realizadas', value: '${(_compras ?? []).length}')),
            ],
          ),
        if (verCompras) ...[
          const SizedBox(height: 10),
          _StatCard(label: 'Total gastado', value: '${_totalGastado.toStringAsFixed(2)} Bs', fullWidth: true),
        ],
        if (verReservas) ...[
          const SizedBox(height: 20),
          _ResumenBloque(
            titulo: 'Ultimas reservas',
            vacio: 'Todavia no tienes reservas.',
            cargando: _cargandoReservas,
            items: (_reservas ?? []).take(3).map((r) {
              final primero = r.detalles.isNotEmpty ? r.detalles.first.productoNombre : '';
              final etiqueta = r.detalles.length > 1 ? '$primero y mas' : primero;
              return _MiniItem(texto: etiqueta, estado: r.estado);
            }).toList(),
          ),
        ],
        if (verCompras) ...[
          const SizedBox(height: 16),
          _ResumenBloque(
            titulo: 'Ultimas compras',
            vacio: 'Todavia no tienes compras.',
            cargando: _cargandoCompras,
            items: (_compras ?? []).take(3).map((v) {
              return _MiniItem(texto: '#${v.id} · ${v.total.toStringAsFixed(2)} Bs', estado: v.estadoPago);
            }).toList(),
          ),
        ],
      ],
    );
  }

  Widget _buildReservas() {
    if (_cargandoReservas) return const Center(child: CircularProgressIndicator());
    final reservas = _reservas ?? [];
    if (reservas.isEmpty) {
      return const Center(child: Text('Todavia no tienes reservas.', style: TextStyle(color: AppColors.grayText)));
    }
    return RefreshIndicator(
      onRefresh: _cargarReservas,
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: reservas.length,
        separatorBuilder: (_, _) => const SizedBox(height: 12),
        itemBuilder: (context, i) {
          final r = reservas[i];
          return _DashCard(
            titulo: r.sucursalNombre,
            subtitulo: _fmtFecha(r.horarioAtencion),
            detalles: [for (final d in r.detalles) '${d.cantidad}x ${d.productoNombre} (${d.tallaCodigo}, ${d.colorNombre})'],
            estado: r.estado,
            accion: r.cancelable
                ? OutlinedButton(
                    onPressed: _procesandoReservaId == r.id ? null : () => _cancelarReserva(r),
                    style: OutlinedButton.styleFrom(
                      shape: const RoundedRectangleBorder(),
                      side: const BorderSide(color: Color(0xFFF3C9C5)),
                      foregroundColor: AppColors.danger,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    ),
                    child: Text(_procesandoReservaId == r.id ? '...' : 'CANCELAR', style: const TextStyle(fontSize: 11)),
                  )
                : null,
          );
        },
      ),
    );
  }

  Widget _buildCompras() {
    if (_cargandoCompras) return const Center(child: CircularProgressIndicator());
    final compras = _compras ?? [];
    if (compras.isEmpty) {
      return const Center(child: Text('Todavia no tienes compras.', style: TextStyle(color: AppColors.grayText)));
    }
    return RefreshIndicator(
      onRefresh: _cargarCompras,
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: compras.length,
        separatorBuilder: (_, _) => const SizedBox(height: 12),
        itemBuilder: (context, i) {
          final v = compras[i];
          return Container(
            decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Compra #${v.id} · ${v.total.toStringAsFixed(2)} Bs',
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: AppColors.brandDark),
                      ),
                    ),
                    _EstadoBadge(v.estadoPago),
                  ],
                ),
                const SizedBox(height: 4),
                Text('${_fmtFecha(v.fecha)} · ${v.sucursalNombre}', style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                const SizedBox(height: 8),
                for (final d in v.detalles)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(
                      '${d.cantidad}x ${d.productoNombre} (${d.tallaCodigo}, ${d.colorNombre})',
                      style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark),
                    ),
                  ),
                if (v.completada) ...[
                  const Divider(height: 24),
                  if (v.tieneDevolucion) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF4E0),
                        border: Border.all(color: const Color(0xFFF6C87D)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.assignment_return_outlined, size: 16, color: Color(0xFFB26A00)),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'DEVOLUCIÓN: ${(v.estadoDevolucion ?? "solicitada").toUpperCase()}',
                              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 11, color: Color(0xFFB26A00), letterSpacing: 0.5),
                            ),
                          ),
                          if (v.montoDevolucion != null)
                            Text(
                              '${v.montoDevolucion!.toStringAsFixed(2)} Bs',
                              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 11, color: Color(0xFFB26A00)),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                  ] else if (v.puedeDevolver) ...[
                    OutlinedButton.icon(
                      onPressed: () => _abrirSolicitarDevolucion(v),
                      icon: const Icon(Icons.assignment_return_outlined, size: 16, color: Color(0xFFA05E03)),
                      label: Text(
                        'SOLICITAR DEVOLUCIÓN (${v.tiempoRestanteDevolucion})',
                        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Color(0xFFA05E03)),
                      ),
                      style: OutlinedButton.styleFrom(
                        backgroundColor: const Color(0xFFFFF8EB),
                        side: const BorderSide(color: Color(0xFFF6C87D)),
                        shape: const RoundedRectangleBorder(),
                        minimumSize: const Size.fromHeight(38),
                      ),
                    ),
                    const SizedBox(height: 10),
                  ] else ...[
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 4),
                      child: Text(
                        'Plazo de devolución vencido (24h)',
                        style: TextStyle(fontSize: 11, fontStyle: FontStyle.italic, color: AppColors.grayText),
                      ),
                    ),
                    const SizedBox(height: 6),
                  ],
                  if (v.calificada)
                    _EstrellasVista(estrellas: v.calificacionEstrellas!, comentario: v.calificacionComentario)
                  else if (_calificandoVentaId == v.id)
                    _CalificarForm(
                      estrellas: _estrellas,
                      comentarioCtrl: _comentarioCtrl,
                      guardando: _guardandoCalificacion,
                      error: _errorCalificacion,
                      onSeleccionarEstrella: (n) => setState(() => _estrellas = n),
                      onCancelar: () => setState(() => _calificandoVentaId = null),
                      onEnviar: () => _enviarCalificacion(v),
                    )
                  else
                    OutlinedButton(
                      onPressed: () => _abrirCalificar(v),
                      style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder(), minimumSize: const Size.fromHeight(40)),
                      child: const Text('CALIFICAR ESTA COMPRA'),
                    ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildPagos() {
    final metodos = _metodosUsados;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'Por tu seguridad no guardamos numeros de tarjeta -- cuando pagas con tarjeta, eso pasa directo por PayPal '
          'y nunca llega a nuestros servidores. Aca ves con que metodos pagaste antes.',
          style: TextStyle(fontSize: 12, color: AppColors.grayText),
        ),
        const SizedBox(height: 16),
        if (_cargandoCompras)
          const Center(child: Padding(padding: EdgeInsets.only(top: 20), child: CircularProgressIndicator()))
        else if (metodos.isEmpty)
          const Text('Todavia no registras ningun pago.', style: TextStyle(fontSize: 13, color: AppColors.grayText))
        else
          for (final m in metodos)
            Container(
              margin: const EdgeInsets.only(bottom: 12),
              decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_metodoLabel[m.key] ?? m.key, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: AppColors.brandDark)),
                  const SizedBox(height: 4),
                  Text('Usado ${m.value} ${m.value == 1 ? 'vez' : 'veces'}', style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                ],
              ),
            ),
      ],
    );
  }

  Widget _buildNotificaciones() {
    final notificaciones = ref.watch(notificacionesProvider);
    final noLeidas = ref.watch(notificacionesNoLeidasProvider);

    if (notificaciones.isEmpty) {
      return const Center(child: Text('Todavia no tienes notificaciones.', style: TextStyle(color: AppColors.grayText)));
    }
    return Column(
      children: [
        if (noLeidas > 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => ref.read(notificacionesProvider.notifier).marcarTodasLeidas(),
                child: const Text('MARCAR TODAS COMO LEIDAS', style: TextStyle(color: AppColors.brandDark, fontSize: 11)),
              ),
            ),
          ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () => ref.read(notificacionesProvider.notifier).cargar(),
            child: ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: notificaciones.length,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (context, i) {
                final n = notificaciones[i];
                return _NotifCard(notificacion: n, onTap: () => ref.read(notificacionesProvider.notifier).marcarLeida(n.id));
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDatos(Usuario usuario) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        if (_errorPerfil != null) _ErrorBanner(_errorPerfil!),
        if (_successPerfil != null) _SuccessBanner(_successPerfil!),
        TextField(controller: _nombreCtrl, decoration: const InputDecoration(labelText: 'NOMBRE COMPLETO')),
        const SizedBox(height: 14),
        TextFormField(initialValue: usuario.email, enabled: false, decoration: const InputDecoration(labelText: 'CORREO ELECTRONICO')),
        const SizedBox(height: 14),
        TextField(controller: _telefonoCtrl, decoration: const InputDecoration(labelText: 'TELEFONO')),
        const SizedBox(height: 14),
        TextField(controller: _direccionCtrl, decoration: const InputDecoration(labelText: 'DIRECCION')),
        const SizedBox(height: 20),
        ElevatedButton(
          onPressed: _savingPerfil ? null : _guardarPerfil,
          child: Text(_savingPerfil ? 'GUARDANDO...' : 'GUARDAR CAMBIOS'),
        ),
      ],
    );
  }

  Widget _buildSeguridad() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        if (_errorPassword != null) _ErrorBanner(_errorPassword!),
        if (_successPassword != null) _SuccessBanner(_successPassword!),
        TextField(controller: _actualCtrl, obscureText: true, decoration: const InputDecoration(labelText: 'CONTRASENA ACTUAL')),
        const SizedBox(height: 14),
        TextField(
          controller: _nuevaCtrl,
          obscureText: true,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(labelText: 'NUEVA CONTRASENA'),
        ),
        const SizedBox(height: 10),
        PasswordStrengthChecklist(password: _nuevaCtrl.text),
        const SizedBox(height: 20),
        OutlinedButton(
          onPressed: _savingPassword ? null : _cambiarPassword,
          child: Text(_savingPassword ? 'GUARDANDO...' : 'ACTUALIZAR CONTRASENA'),
        ),
      ],
    );
  }

  // ---------------------------------------------------------- Staff (simple)

  Widget _buildStaff(Usuario? usuario) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        TextButton.icon(
          onPressed: () => context.go('/admin'),
          icon: const Icon(Icons.arrow_back, size: 16),
          label: const Text('VOLVER AL PANEL'),
          style: TextButton.styleFrom(foregroundColor: AppColors.brandDark, padding: EdgeInsets.zero),
        ),
        const SizedBox(height: 8),
        const Text('Actualiza tus datos personales y tu contrasena.', style: TextStyle(fontSize: 13, color: AppColors.grayTextDark)),
        const SizedBox(height: 24),
        const EyebrowText('Datos personales'),
        const SizedBox(height: 12),
        if (_errorPerfil != null) _ErrorBanner(_errorPerfil!),
        if (_successPerfil != null) _SuccessBanner(_successPerfil!),
        TextField(controller: _nombreCtrl, decoration: const InputDecoration(labelText: 'NOMBRE')),
        const SizedBox(height: 14),
        TextFormField(initialValue: usuario?.email, enabled: false, decoration: const InputDecoration(labelText: 'CORREO')),
        const SizedBox(height: 20),
        ElevatedButton(
          onPressed: _savingPerfil ? null : _guardarPerfil,
          child: Text(_savingPerfil ? 'GUARDANDO...' : 'GUARDAR CAMBIOS'),
        ),
        const SizedBox(height: 36),
        const EyebrowText('Cambiar contrasena'),
        const SizedBox(height: 12),
        if (_errorPassword != null) _ErrorBanner(_errorPassword!),
        if (_successPassword != null) _SuccessBanner(_successPassword!),
        TextField(controller: _actualCtrl, obscureText: true, decoration: const InputDecoration(labelText: 'CONTRASENA ACTUAL')),
        const SizedBox(height: 14),
        TextField(
          controller: _nuevaCtrl,
          obscureText: true,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(labelText: 'NUEVA CONTRASENA'),
        ),
        const SizedBox(height: 10),
        PasswordStrengthChecklist(password: _nuevaCtrl.text),
        const SizedBox(height: 20),
        OutlinedButton(
          onPressed: _savingPassword ? null : _cambiarPassword,
          child: Text(_savingPassword ? 'GUARDANDO...' : 'ACTUALIZAR CONTRASENA'),
        ),
      ],
    );
  }
}

String _fmtFecha(DateTime d) =>
    '${d.day}/${d.month}/${d.year} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

(Color, Color) _badgeColors(String estado) {
  switch (estado) {
    case 'pendiente':
    case 'verificando':
    case 'solicitada':
      return (const Color(0xFFB26A00), const Color(0xFFFFF4E0));
    case 'rechazado':
    case 'rechazada':
    case 'cancelada':
    case 'vencida':
      return (AppColors.danger, AppColors.dangerBg);
    case 'completado':
    case 'pagada':
    case 'completada':
    case 'confirmada':
      return (AppColors.success, AppColors.successBg);
    default:
      return (AppColors.grayTextDark, AppColors.grayBorderLight);
  }
}

class _TabsBar extends StatelessWidget {
  const _TabsBar({required this.tab, required this.noLeidas, required this.visibleTabs, required this.onSelect});

  final _Tab tab;
  final int noLeidas;
  final List<_Tab> visibleTabs;
  final ValueChanged<_Tab> onSelect;

  static const _labels = {
    _Tab.resumen: 'Resumen',
    _Tab.reservas: 'Mis Reservas',
    _Tab.compras: 'Mis Compras',
    _Tab.pagos: 'Metodos de Pago',
    _Tab.notificaciones: 'Notificaciones',
    _Tab.datos: 'Mis Datos',
    _Tab.seguridad: 'Seguridad',
  };

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.grayBorderLight))),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Row(
          children: [
            for (final t in visibleTabs)
              _TabButton(
                label: _labels[t]!,
                selected: t == tab,
                badge: t == _Tab.notificaciones && noLeidas > 0 ? noLeidas : null,
                onTap: () => onSelect(t),
              ),
          ],
        ),
      ),
    );
  }
}

class _TabButton extends StatelessWidget {
  const _TabButton({required this.label, required this.selected, required this.onTap, this.badge});

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final int? badge;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.brandDark : AppColors.grayText;
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: selected ? AppColors.brandDark : Colors.transparent, width: 2))),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label.toUpperCase(),
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.3, color: color),
            ),
            if (badge != null) ...[
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: const BoxDecoration(color: Color(0xFFD32F2F), shape: BoxShape.circle),
                constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                child: Text('$badge', textAlign: TextAlign.center, style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.label, required this.value, this.fullWidth = false});

  final String label;
  final String value;
  final bool fullWidth;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: fullWidth ? double.infinity : null,
      decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label.toUpperCase(), style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.4, color: AppColors.grayText)),
          const SizedBox(height: 6),
          Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppColors.brandDark)),
        ],
      ),
    );
  }
}

class _ResumenBloque extends StatelessWidget {
  const _ResumenBloque({required this.titulo, required this.vacio, required this.cargando, required this.items});

  final String titulo;
  final String vacio;
  final bool cargando;
  final List<_MiniItem> items;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo.toUpperCase(), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.3, color: AppColors.brandDark)),
          const SizedBox(height: 10),
          if (cargando)
            const Padding(padding: EdgeInsets.symmetric(vertical: 8), child: Center(child: CircularProgressIndicator()))
          else if (items.isEmpty)
            Text(vacio, style: const TextStyle(fontSize: 13, color: AppColors.grayText))
          else
            for (final item in items) item,
        ],
      ),
    );
  }
}

class _MiniItem extends StatelessWidget {
  const _MiniItem({required this.texto, required this.estado});

  final String texto;
  final String estado;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFF5F5F5)))),
      child: Row(
        children: [
          Expanded(child: Text(texto, style: const TextStyle(fontSize: 13, color: AppColors.brandDark))),
          const SizedBox(width: 8),
          _EstadoBadge(estado),
        ],
      ),
    );
  }
}

class _EstadoBadge extends StatelessWidget {
  const _EstadoBadge(this.estado);
  final String estado;

  @override
  Widget build(BuildContext context) {
    final (fg, bg) = _badgeColors(estado);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      color: bg,
      child: Text(estado.toUpperCase(), style: TextStyle(color: fg, fontSize: 10, fontWeight: FontWeight.w700)),
    );
  }
}

class _DashCard extends StatelessWidget {
  const _DashCard({required this.titulo, required this.subtitulo, required this.detalles, required this.estado, this.accion});

  final String titulo;
  final String subtitulo;
  final List<String> detalles;
  final String estado;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(titulo, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: AppColors.brandDark)),
                const SizedBox(height: 2),
                Text(subtitulo, style: const TextStyle(fontSize: 12, color: AppColors.grayText)),
                const SizedBox(height: 6),
                for (final d in detalles)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(d, style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              _EstadoBadge(estado),
              if (accion != null) ...[const SizedBox(height: 8), accion!],
            ],
          ),
        ],
      ),
    );
  }
}

class _NotifCard extends StatelessWidget {
  const _NotifCard({required this.notificacion, required this.onTap});

  final Notificacion notificacion;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        color: notificacion.leida ? null : const Color(0xFFF5F8F7),
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(notificacion.mensaje, style: const TextStyle(fontSize: 13, color: AppColors.brandDark)),
                  const SizedBox(height: 4),
                  Text(_fmtFecha(notificacion.fechaEnvio), style: const TextStyle(fontSize: 11, color: AppColors.grayText)),
                ],
              ),
            ),
            if (!notificacion.leida) Container(width: 8, height: 8, decoration: const BoxDecoration(color: AppColors.brandDark, shape: BoxShape.circle)),
          ],
        ),
      ),
    );
  }
}

class _EstrellasVista extends StatelessWidget {
  const _EstrellasVista({required this.estrellas, this.comentario});

  final int estrellas;
  final String? comentario;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: List.generate(
            5,
            (i) => Icon(i < estrellas ? Icons.star : Icons.star_border, size: 18, color: const Color(0xFFE8B923)),
          ),
        ),
        if (comentario != null && comentario!.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text('"$comentario"', style: const TextStyle(fontSize: 12, fontStyle: FontStyle.italic, color: AppColors.grayTextDark)),
        ],
      ],
    );
  }
}

class _CalificarForm extends StatelessWidget {
  const _CalificarForm({
    required this.estrellas,
    required this.comentarioCtrl,
    required this.guardando,
    required this.error,
    required this.onSeleccionarEstrella,
    required this.onCancelar,
    required this.onEnviar,
  });

  final int estrellas;
  final TextEditingController comentarioCtrl;
  final bool guardando;
  final String? error;
  final ValueChanged<int> onSeleccionarEstrella;
  final VoidCallback onCancelar;
  final VoidCallback onEnviar;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (error != null) ...[
          Container(
            padding: const EdgeInsets.all(10),
            color: AppColors.dangerBg,
            child: Text(error!, style: const TextStyle(color: AppColors.danger, fontSize: 12)),
          ),
          const SizedBox(height: 10),
        ],
        Row(
          children: List.generate(
            5,
            (i) => IconButton(
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
              onPressed: () => onSeleccionarEstrella(i + 1),
              icon: Icon(i < estrellas ? Icons.star : Icons.star_border, color: const Color(0xFFE8B923), size: 26),
            ),
          ),
        ),
        TextField(
          controller: comentarioCtrl,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Contanos tu experiencia (opcional)'),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: onCancelar,
                style: OutlinedButton.styleFrom(shape: const RoundedRectangleBorder()),
                child: const Text('CANCELAR'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: ElevatedButton(
                onPressed: (estrellas < 1 || guardando) ? null : onEnviar,
                style: ElevatedButton.styleFrom(backgroundColor: AppColors.brandDark, shape: const RoundedRectangleBorder()),
                child: Text(guardando ? 'ENVIANDO...' : 'ENVIAR'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner(this.message);
  final String message;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(12),
    margin: const EdgeInsets.only(bottom: 14),
    color: AppColors.dangerBg,
    child: Text(message, style: const TextStyle(color: AppColors.danger, fontSize: 13)),
  );
}

class _SuccessBanner extends StatelessWidget {
  const _SuccessBanner(this.message);
  final String message;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(12),
    margin: const EdgeInsets.only(bottom: 14),
    color: AppColors.successBg,
    child: Text(message, style: const TextStyle(color: AppColors.success, fontSize: 13)),
  );
}

class _SolicitarDevolucionSheet extends ConsumerStatefulWidget {
  const _SolicitarDevolucionSheet({
    required this.venta,
    required this.onSuccess,
  });

  final Venta venta;
  final VoidCallback onSuccess;

  @override
  ConsumerState<_SolicitarDevolucionSheet> createState() => _SolicitarDevolucionSheetState();
}

class _SolicitarDevolucionSheetState extends ConsumerState<_SolicitarDevolucionSheet> {
  late Map<int, bool> _seleccionados;
  late Map<int, int> _cantidades;
  String _motivo = 'defecto';
  String _metodoReembolso = 'mismo_medio';
  final _obsCtrl = TextEditingController();
  bool _guardando = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _seleccionados = {for (final d in widget.venta.detalles) d.id: true};
    _cantidades = {for (final d in widget.venta.detalles) d.id: d.cantidad};
  }

  @override
  void dispose() {
    _obsCtrl.dispose();
    super.dispose();
  }

  double get _montoTotal {
    double total = 0.0;
    for (final d in widget.venta.detalles) {
      if (_seleccionados[d.id] == true) {
        total += d.precioUnitario * (_cantidades[d.id] ?? d.cantidad);
      }
    }
    return total;
  }

  bool get _haySeleccionados {
    return widget.venta.detalles.any((d) => _seleccionados[d.id] == true && (_cantidades[d.id] ?? 0) > 0);
  }

  Future<void> _confirmar() async {
    final items = widget.venta.detalles
        .where((d) => _seleccionados[d.id] == true && (_cantidades[d.id] ?? 0) > 0)
        .map((d) => {
              'item_linea_id': d.id,
              'cantidad_devuelta': _cantidades[d.id] ?? d.cantidad,
            })
        .toList();

    if (items.isEmpty) {
      setState(() => _error = 'Debes seleccionar al menos una prenda a devolver.');
      return;
    }

    final todos = widget.venta.detalles.every(
      (d) => _seleccionados[d.id] == true && (_cantidades[d.id] ?? 0) == d.cantidad,
    );
    final tipo = todos ? 'total' : 'parcial';

    setState(() {
      _guardando = true;
      _error = null;
    });

    try {
      await ref.read(ventasRepositoryProvider).solicitarDevolucion(
            ventaId: widget.venta.id,
            motivo: _motivo,
            tipo: tipo,
            metodoReembolso: _metodoReembolso,
            observaciones: _obsCtrl.text.trim().isEmpty ? null : _obsCtrl.text.trim(),
            items: items,
          );

      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Tu solicitud de devolución fue enviada con éxito.'),
          backgroundColor: AppColors.success,
        ),
      );
      widget.onSuccess();
    } catch (e) {
      if (mounted) setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.brandWhite,
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.88,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 12, 12),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'SOLICITAR DEVOLUCIÓN',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: AppColors.brandDark,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Compra #${widget.venta.id} · Plazo de 24 horas',
                        style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: const BoxDecoration(
                      color: Color(0xFFFFF8EB),
                      border: Border(left: BorderSide(color: Color(0xFFF59E0B), width: 4)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.access_time, size: 18, color: Color(0xFFD97706)),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            'Ventana de 24h activa: Te quedan ${widget.venta.tiempoRestanteDevolucion} para solicitar devolución. Marca las prendas a devolver.',
                            style: const TextStyle(fontSize: 12, color: Color(0xFF854D0E), height: 1.3),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_error != null) ...[
                    _ErrorBanner(_error!),
                    const SizedBox(height: 10),
                  ],
                  const Text(
                    'PRENDAS A DEVOLVER:',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.grayText, letterSpacing: 0.5),
                  ),
                  const SizedBox(height: 8),
                  for (final d in widget.venta.detalles) ...[
                    Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: _seleccionados[d.id] == true ? AppColors.brandDark : AppColors.grayBorderLight,
                        ),
                        color: _seleccionados[d.id] == true ? const Color(0xFFFAFAFA) : AppColors.brandWhite,
                      ),
                      child: Row(
                        children: [
                          Checkbox(
                            value: _seleccionados[d.id] ?? false,
                            activeColor: AppColors.brandDark,
                            onChanged: (val) {
                              setState(() => _seleccionados[d.id] = val ?? false);
                            },
                          ),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  d.productoNombre,
                                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: AppColors.brandDark),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  '${d.tallaCodigo} · ${d.colorNombre} · ${d.precioUnitario.toStringAsFixed(2)} Bs c/u',
                                  style: const TextStyle(fontSize: 11, color: AppColors.grayTextDark),
                                ),
                              ],
                            ),
                          ),
                          if (_seleccionados[d.id] == true)
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.remove_circle_outline, size: 20),
                                  onPressed: (_cantidades[d.id] ?? d.cantidad) > 1
                                      ? () {
                                          setState(() => _cantidades[d.id] = (_cantidades[d.id] ?? d.cantidad) - 1);
                                        }
                                      : null,
                                ),
                                Text(
                                  '${_cantidades[d.id] ?? d.cantidad}/${d.cantidad}',
                                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.add_circle_outline, size: 20),
                                  onPressed: (_cantidades[d.id] ?? d.cantidad) < d.cantidad
                                      ? () {
                                          setState(() => _cantidades[d.id] = (_cantidades[d.id] ?? d.cantidad) + 1);
                                        }
                                      : null,
                                ),
                              ],
                            ),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  const Text(
                    'MOTIVO DE LA DEVOLUCIÓN',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.grayText, letterSpacing: 0.5),
                  ),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String>(
                    initialValue: _motivo,
                    decoration: const InputDecoration(
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'defecto', child: Text('Defecto de fábrica o costura')),
                      DropdownMenuItem(value: 'talla_incorrecta', child: Text('Talla no me quedó / Talla equivocada')),
                      DropdownMenuItem(value: 'insatisfaccion', child: Text('No cumple expectativas / Insatisfacción')),
                      DropdownMenuItem(value: 'otro', child: Text('Otro motivo')),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => _motivo = val);
                    },
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'MÉTODO DE REEMBOLSO PREFERIDO',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.grayText, letterSpacing: 0.5),
                  ),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String>(
                    initialValue: _metodoReembolso,
                    decoration: const InputDecoration(
                      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'mismo_medio', child: Text('Mismo medio de pago original')),
                      DropdownMenuItem(value: 'credito_tienda', child: Text('Crédito en tienda / Vale para compras')),
                      DropdownMenuItem(value: 'efectivo', child: Text('Efectivo en sucursal de retiro')),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => _metodoReembolso = val);
                    },
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'OBSERVACIONES (OPCIONAL)',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.grayText, letterSpacing: 0.5),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: _obsCtrl,
                    maxLines: 2,
                    decoration: const InputDecoration(
                      hintText: 'Cuéntanos brevemente qué ocurrió con las prendas...',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    color: const Color(0xFFF7F7F7),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Total a reembolsar:',
                          style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: AppColors.brandCharcoal),
                        ),
                        Text(
                          '${_montoTotal.toStringAsFixed(2)} Bs',
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: AppColors.brandDark),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _guardando ? null : () => Navigator.of(context).pop(),
                          style: OutlinedButton.styleFrom(
                            shape: const RoundedRectangleBorder(),
                            minimumSize: const Size.fromHeight(44),
                          ),
                          child: const Text('CANCELAR'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        flex: 2,
                        child: ElevatedButton(
                          onPressed: (!_haySeleccionados || _guardando) ? null : _confirmar,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppColors.brandDark,
                            foregroundColor: AppColors.brandWhite,
                            shape: const RoundedRectangleBorder(),
                            minimumSize: const Size.fromHeight(44),
                          ),
                          child: Text(
                            _guardando ? 'ENVIANDO...' : 'CONFIRMAR SOLICITUD',
                            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
