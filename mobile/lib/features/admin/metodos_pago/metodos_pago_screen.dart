import 'dart:convert';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/api_client.dart';
import '../../auth/auth_provider.dart';
import '../widgets/admin_widgets.dart';
import '../widgets/dialogos.dart';

const _tipos = {
  'paypal': 'PayPal',
  'qr': 'QR',
  'transferencia': 'Transferencia bancaria',
  'otro': 'Otro',
  'contra_entrega': 'Contra entrega (sin conexión)',
};

/// CU21 Gestionar metodos de pago (`/admin/metodos-pago` de la web): como le
/// pagan a la tienda (PayPal con sus credenciales, QR, transferencia u otro).
class MetodosPagoScreen extends ConsumerStatefulWidget {
  const MetodosPagoScreen({super.key});

  @override
  ConsumerState<MetodosPagoScreen> createState() => _MetodosPagoScreenState();
}

class _MetodosPagoScreenState extends ConsumerState<MetodosPagoScreen> {
  List<Map<String, dynamic>> _metodos = [];
  bool _cargando = true;
  String? _error;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final r = await _dio.get('/metodos-pago');
      setState(() {
        _metodos = (r.data as List).cast<Map<String, dynamic>>();
        _error = null;
      });
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  // Lo que el backend espera (MetodoPagoIn) a partir de un metodo existente.
  Map<String, dynamic> _cuerpo(Map<String, dynamic> m) => {
        for (final k in ['tipo', 'nombre', 'instrucciones', 'activo', 'orden', 'paypal_client_id', 'paypal_modo', 'paypal_email',
          'banco', 'numero_cuenta', 'tipo_cuenta', 'titular', 'documento_titular'])
          k: m[k],
      };

  Future<void> _alternar(Map<String, dynamic> m) async {
    try {
      await _dio.put('/metodos-pago/${m['id']}', data: {..._cuerpo(m), 'activo': !(m['activo'] == true)});
      _cargar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  Future<void> _borrar(Map<String, dynamic> m) async {
    if (!await confirmarDialogo(context, '¿Borrar el método «${m['nombre']}»?', si: 'Borrar', peligro: true)) return;
    try {
      await _dio.delete('/metodos-pago/${m['id']}');
      _cargar();
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    }
  }

  Future<void> _editar([Map<String, dynamic>? m]) async {
    final guardado = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => _FormularioMetodo(metodo: m, dio: _dio)),
    );
    if (guardado == true) _cargar();
  }

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: 'METODOS DE PAGO',
      floatingActionButton: FloatingActionButton(onPressed: () => _editar(), child: const Icon(Icons.add)),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _cargar,
              child: ListView(padding: const EdgeInsets.only(bottom: 90), children: [
                if (_error != null) AdminErrorBanner(message: _error!),
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('Cómo te pagan los clientes. PayPal se confirma solo; QR, transferencia y otros llevan '
                      'comprobante que el personal aprueba.'),
                ),
                if (_metodos.isEmpty) const Padding(padding: EdgeInsets.all(24), child: Text('Todavía no hay métodos de pago.')),
                for (final m in _metodos)
                  AdminCard(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Expanded(
                          child: Text(m['nombre'].toString(), style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                        ),
                        NeutralBadge(_tipos[m['tipo']] ?? m['tipo'].toString()),
                      ]),
                      if (m['instrucciones'] != null) Text(m['instrucciones'].toString(), style: const TextStyle(fontSize: 12.5)),
                      if (m['tipo'] == 'paypal')
                        AdminInfoRow('PayPal', '${m['paypal_modo'] ?? '—'} · ${m['paypal_email'] ?? 'sin correo'} · '
                            'secret ${m['paypal_secret_mascara'] ?? 'no cargado'}'),
                      if (m['tipo'] == 'transferencia')
                        AdminInfoRow('Cuenta', '${m['banco'] ?? ''} ${m['numero_cuenta'] ?? ''} · ${m['titular'] ?? ''}'),
                      if (m['qr_url'] != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: CachedNetworkImage(imageUrl: m['qr_url'].toString(), height: 90),
                        ),
                      Row(children: [
                        Switch(value: m['activo'] == true, onChanged: (_) => _alternar(m)),
                        Text(m['activo'] == true ? 'Activo' : 'Pausado'),
                        const Spacer(),
                        IconButton(icon: const Icon(Icons.edit_outlined), onPressed: () => _editar(m)),
                        IconButton(icon: const Icon(Icons.delete_outline, color: Color(0xFFB3261E)), onPressed: () => _borrar(m)),
                      ]),
                    ]),
                  ),
              ]),
            ),
    );
  }
}

class _FormularioMetodo extends StatefulWidget {
  const _FormularioMetodo({required this.metodo, required this.dio});
  final Map<String, dynamic>? metodo;
  final Dio dio;

  @override
  State<_FormularioMetodo> createState() => _FormularioMetodoState();
}

class _FormularioMetodoState extends State<_FormularioMetodo> {
  late String _tipo = widget.metodo?['tipo']?.toString() ?? 'qr';
  late bool _activo = widget.metodo?['activo'] != false;
  late String _modo = widget.metodo?['paypal_modo']?.toString() ?? 'sandbox';
  final Map<String, TextEditingController> _c = {};
  String? _qr;
  bool _guardando = false;
  String? _error;

  TextEditingController _campo(String k) =>
      _c.putIfAbsent(k, () => TextEditingController(text: widget.metodo?[k]?.toString() ?? ''));

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _elegirQr() async {
    final f = await ImagePicker().pickImage(source: ImageSource.gallery, maxWidth: 1000, imageQuality: 85);
    if (f == null) return;
    final bytes = await f.readAsBytes();
    final tipo = f.name.toLowerCase().endsWith('.png') ? 'png' : 'jpeg';
    setState(() => _qr = 'data:image/$tipo;base64,${base64Encode(bytes)}');
  }

  String? _v(String k) => _campo(k).text.trim().isEmpty ? null : _campo(k).text.trim();

  Future<void> _guardar() async {
    setState(() {
      _guardando = true;
      _error = null;
    });
    final cuerpo = {
      'tipo': _tipo,
      'nombre': _campo('nombre').text.trim(),
      'instrucciones': _v('instrucciones'),
      'activo': _activo,
      'orden': int.tryParse(_campo('orden').text) ?? 0,
      if (_tipo == 'paypal') ...{
        'paypal_client_id': _v('paypal_client_id'),
        'paypal_secret': _v('paypal_secret'),
        'paypal_modo': _modo,
        'paypal_email': _v('paypal_email'),
      },
      if (_tipo == 'transferencia') ...{
        for (final k in ['banco', 'numero_cuenta', 'tipo_cuenta', 'titular', 'documento_titular']) k: _v(k),
      },
      if (_qr != null) 'qr_imagen': _qr,
    };
    try {
      final id = widget.metodo?['id'];
      if (id == null) {
        await widget.dio.post('/metodos-pago', data: cuerpo);
      } else {
        await widget.dio.put('/metodos-pago/$id', data: cuerpo);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  Widget _texto(String k, String etiqueta, {bool oculto = false, int lineas = 1, String? ayuda}) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: TextField(
          controller: _campo(k),
          obscureText: oculto,
          maxLines: lineas,
          decoration: InputDecoration(labelText: etiqueta, helperText: ayuda),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return AdminScaffold(
      title: widget.metodo == null ? 'NUEVO METODO' : 'EDITAR METODO',
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (_error != null) AdminErrorBanner(message: _error!),
        DropdownButtonFormField<String>(
          value: _tipo,
          decoration: const InputDecoration(labelText: 'Tipo'),
          items: [for (final e in _tipos.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
          onChanged: widget.metodo == null ? (v) => setState(() => _tipo = v ?? _tipo) : null,
        ),
        const SizedBox(height: 12),
        _texto('nombre', 'Nombre (lo ve el cliente)'),
        _texto('instrucciones', 'Instrucciones (opcional)', lineas: 3),
        if (_tipo == 'paypal') ...[
          _texto('paypal_client_id', 'Client ID de PayPal'),
          _texto('paypal_secret', 'Secret de PayPal', oculto: true,
              ayuda: widget.metodo == null ? null : 'Déjalo vacío para mantener el que ya está.'),
          DropdownButtonFormField<String>(
            value: _modo,
            decoration: const InputDecoration(labelText: 'Modo'),
            items: const [
              DropdownMenuItem(value: 'sandbox', child: Text('Sandbox (pruebas)')),
              DropdownMenuItem(value: 'live', child: Text('Live (real)')),
            ],
            onChanged: (v) => setState(() => _modo = v ?? _modo),
          ),
          const SizedBox(height: 12),
          _texto('paypal_email', 'Correo PayPal (para recibir la liquidación)'),
        ],
        if (_tipo == 'qr') ...[
          OutlinedButton.icon(onPressed: _elegirQr, icon: const Icon(Icons.qr_code), label: Text(_qr == null ? 'ELEGIR IMAGEN DEL QR' : 'QR ELEGIDO ✓')),
          if (widget.metodo?['qr_url'] != null && _qr == null)
            Padding(padding: const EdgeInsets.only(top: 8), child: CachedNetworkImage(imageUrl: widget.metodo!['qr_url'].toString(), height: 120)),
          const SizedBox(height: 12),
        ],
        if (_tipo == 'transferencia') ...[
          _texto('banco', 'Banco'),
          _texto('numero_cuenta', 'Número de cuenta'),
          _texto('tipo_cuenta', 'Tipo de cuenta'),
          _texto('titular', 'Titular'),
          _texto('documento_titular', 'CI / NIT del titular'),
        ],
        _texto('orden', 'Orden en el checkout (0 = primero)'),
        SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text('Activo'), value: _activo, onChanged: (v) => setState(() => _activo = v)),
        const SizedBox(height: 8),
        FilledButton(
          style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
          onPressed: _guardando ? null : _guardar,
          child: Text(_guardando ? 'GUARDANDO...' : 'GUARDAR'),
        ),
      ]),
    );
  }
}
