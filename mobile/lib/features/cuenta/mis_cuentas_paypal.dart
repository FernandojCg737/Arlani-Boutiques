import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_client.dart';
import '../../core/api_config.dart';
import '../auth/auth_provider.dart';
import '../empezar/panel_paypal.dart';
import 'estilo_cuenta.dart';

/// Cuenta PayPal del cliente (`MetodoPagoClienteOut` del backend).
class _CuentaPaypal {
  _CuentaPaypal(this.j);
  final Map<String, dynamic> j;

  int get id => j['id'] as int;
  String? get cuenta => j['cuenta'] as String?;
  bool get automatica => j['origen'] == 'automatico';
  bool get autorizada => j['autorizada'] == true;
  int get vecesUsado => (j['veces_usado'] as num?)?.toInt() ?? 0;
  DateTime? get ultimoUso => j['ultimo_uso'] == null ? null : DateTime.parse('${j['ultimo_uso']}Z').toLocal();
  List<String> get tiendas => (j['tiendas'] as List? ?? []).map((t) => t.toString()).toList();
}

const _meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/// "Mis cuentas PayPal" (tab Metodos de Pago de `perfil.html` en la web): las
/// cuentas con las que pago y si estan autorizadas para comprar sin conexion.
/// "Autorizar" abre PayPal en un panel dentro de esta misma pantalla.
class MisCuentasPaypal extends ConsumerStatefulWidget {
  const MisCuentasPaypal({super.key});

  @override
  ConsumerState<MisCuentasPaypal> createState() => _MisCuentasPaypalState();
}

class _MisCuentasPaypalState extends ConsumerState<MisCuentasPaypal> {
  List<_CuentaPaypal>? _cuentas;
  bool _procesando = false;
  String? _aviso;
  bool _avisoError = false;
  // Panel de PayPal abierto con el enlace para autorizar.
  String? _panel;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  void _avisar(String texto, {bool error = false}) => setState(() {
        _aviso = texto;
        _avisoError = error;
      });

  void _mostrar(Response r) =>
      _cuentas = [for (final c in (r.data as List).cast<Map<String, dynamic>>()) _CuentaPaypal(c)];

  Future<void> _cargar() async {
    try {
      final r = await _dio.get('/pagos-guardados/metodos');
      if (mounted) setState(() => _mostrar(r));
    } catch (_) {
      // Sin conexion: se ve lo que ya estaba cargado.
      if (mounted) setState(() => _cuentas ??= []);
    }
  }

  Future<void> _autorizar() async {
    setState(() {
      _procesando = true;
      _aviso = null;
    });
    // PayPal vuelve al backend; el panel lo detecta y no llega a cargarlo.
    final backend = Uri.parse(apiBaseUrl).replace(path: '');
    try {
      final r = await _dio.post('/pagos-guardados/paypal/vincular', data: {
        'retorno': backend.replace(path: '/paypal-embed/retorno').toString(),
        'cancelado': backend.replace(path: '/paypal-embed/cancelado').toString(),
      });
      if (mounted) setState(() => _panel = (r.data as Map)['approve_url'].toString());
    } catch (e) {
      if (mounted) _avisar(extractErrorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _alTerminar(String? aprobado) async {
    setState(() => _panel = null);
    if (aprobado == null) {
      _avisar('Cancelaste la autorización. Puedes intentarlo de nuevo cuando quieras.', error: true);
      return;
    }
    setState(() => _procesando = true);
    try {
      final r = await _dio.post('/pagos-guardados/paypal/confirmar');
      if (!mounted) return;
      setState(() => _mostrar(r));
      _avisar('Listo: la cuenta quedó autorizada. Tus compras sin conexión con ella se cobran solas.');
    } catch (e) {
      if (mounted) _avisar(extractErrorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  Future<void> _quitar(_CuentaPaypal c) async {
    final extra = c.autorizada ? ' Las compras sin conexión con esta cuenta que aún no se enviaron no se podrán cobrar.' : '';
    if (!await confirmarCuenta(context, '¿Quitar ${c.cuenta ?? 'esta cuenta PayPal'} de tus métodos de pago?$extra', si: 'Quitar')) {
      return;
    }
    setState(() {
      _procesando = true;
      _aviso = null;
    });
    try {
      final r = await _dio.delete('/pagos-guardados/metodos/${c.id}');
      if (mounted) setState(() => _mostrar(r));
    } catch (e) {
      if (mounted) _avisar(extractErrorMessage(e), error: true);
    } finally {
      if (mounted) setState(() => _procesando = false);
    }
  }

  String _detalle(_CuentaPaypal c) {
    final partes = [c.automatica ? 'Registrada al pagar' : 'Agregada por ti'];
    if (c.vecesUsado > 0) partes.add('usada ${c.vecesUsado} ${c.vecesUsado == 1 ? 'vez' : 'veces'}');
    final u = c.ultimoUso;
    if (u != null) partes.add('última vez el ${u.day} ${_meses[u.month - 1]} de ${u.year}');
    return partes.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final cuentas = _cuentas;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Mis cuentas PayPal', style: GoogleFonts.inter(fontSize: 17, fontWeight: FontWeight.w800, color: tintaCuenta)),
        const SizedBox(height: 6),
        Text(
          'Cada cuenta con la que pagas con PayPal en Arlani se registra aquí sola y queda autorizada para comprar sin '
          'conexión en cualquier tienda. Arlani guarda solo el permiso de PayPal, nunca tus datos.',
          style: GoogleFonts.inter(fontSize: 12.5, height: 1.5, color: grisOscuroCuenta),
        ),
        const SizedBox(height: 14),
        Align(
          alignment: Alignment.centerLeft,
          child: BotonCuenta(_procesando ? 'Abriendo PayPal…' : 'Agregar cuenta PayPal',
              onTap: _procesando || _panel != null ? null : _autorizar),
        ),
        const SizedBox(height: 16),
        if (_aviso != null) AvisoCuenta(_aviso!, error: _avisoError),
        if (_panel != null) ...[
          PanelPaypal(
            key: ValueKey(_panel),
            url: _panel!,
            orderId: 'autorizar',
            alto: (MediaQuery.sizeOf(context).height * 0.75).clamp(460.0, 680.0),
            alTerminar: _alTerminar,
          ),
          const SizedBox(height: 16),
        ],
        if (cuentas == null)
          cargandoCuenta()
        else if (cuentas.isEmpty)
          vacioCuenta('Todavía no tienes cuentas PayPal: se agregan solas cuando pagas con PayPal, o agrégala tú.')
        else
          for (final c in cuentas) ...[_tarjeta(c), const SizedBox(height: 12)],
        Text(
          'Al autorizar, inicia sesión en PayPal con esa misma cuenta. Si entras con otra, se agrega como cuenta nueva.',
          style: GoogleFonts.inter(fontSize: 11.5, height: 1.5, color: grisCuenta),
        ),
      ],
    );
  }

  Widget _tarjeta(_CuentaPaypal c) {
    final conPermiso = c.autorizada || c.tiendas.isNotEmpty;
    return TarjetaCuenta(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('PayPal · ${c.cuenta ?? 'Cuenta PayPal'}',
              style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w700, color: tintaCuenta)),
          const SizedBox(height: 4),
          Text(_detalle(c), style: GoogleFonts.inter(fontSize: 12, color: grisOscuroCuenta)),
          const SizedBox(height: 8),
          InsigniaEstado(
            texto: c.autorizada
                ? 'Autorizada para compras sin conexión en todas las tiendas'
                : c.tiendas.isNotEmpty
                    ? 'Autorizada para compras sin conexión en ${c.tiendas.join(', ')}'
                    : 'Sin autorizar para compras sin conexión',
            tono: conPermiso ? TonoEstado.ok : TonoEstado.espera,
          ),
          if (!c.autorizada && c.tiendas.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text('Queda autorizada en todas las tiendas la próxima vez que pagues con PayPal en Arlani.',
                style: GoogleFonts.inter(fontSize: 11.5, color: grisCuenta)),
          ],
          const SizedBox(height: 12),
          Wrap(spacing: 10, runSpacing: 8, children: [
            // Solo las cuentas sin ningun permiso (registradas antes) se autorizan a mano.
            if (!conPermiso) BotonCuenta('Autorizar', onTap: _procesando || _panel != null ? null : _autorizar),
            BotonCuenta('Quitar', lleno: false, onTap: _procesando ? null : () => _quitar(c)),
          ]),
        ],
      ),
    );
  }
}
