import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/api_client.dart';
import '../auth/auth_provider.dart';
import '../portada/plataforma_data.dart' show colorMarca;

const _noche = Color(0xFF121A2C);
const _gris = Color(0xFF8A8F99);
const _borde = Color(0xFFEDE8E2);

/// CU08 Auditar operaciones (bitacora) del SuperAdministrador: todo el
/// sistema, solo lo de la plataforma o lo de una tienda (como `bitacora.ts`).
class SuperBitacora extends ConsumerStatefulWidget {
  const SuperBitacora({super.key});

  @override
  ConsumerState<SuperBitacora> createState() => _SuperBitacoraState();
}

class _SuperBitacoraState extends ConsumerState<SuperBitacora> {
  // 'todas', 'plataforma' o el id de una tienda.
  Object _filtro = 'todas';
  final _buscar = TextEditingController();
  List<Map<String, dynamic>> _tiendas = [];
  List<Map<String, dynamic>> _items = [];
  int _pagina = 1;
  int _paginas = 1;
  bool _cargando = true;
  String? _error;

  Dio get _dio => ref.read(apiClientProvider).dio;

  @override
  void initState() {
    super.initState();
    _dio.get('/plataforma/empresas').then(
          (r) => mounted ? setState(() => _tiendas = (r.data as List).cast<Map<String, dynamic>>()) : null,
          onError: (_) {},
        );
    _cargar();
  }

  @override
  void dispose() {
    _buscar.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final r = await _dio.get('/bitacora', queryParameters: {
        'page': _pagina,
        'page_size': 20,
        if (_buscar.text.trim().isNotEmpty) 'buscar': _buscar.text.trim(),
        if (_filtro is int) 'empresa_id': _filtro,
        if (_filtro == 'plataforma') 'plataforma': true,
      });
      final datos = r.data as Map<String, dynamic>;
      setState(() {
        _items = (datos['items'] as List).cast<Map<String, dynamic>>();
        final total = datos['total'] as int;
        _paginas = (total / (datos['page_size'] as int)).ceil().clamp(1, 1 << 30);
      });
    } catch (e) {
      setState(() => _error = extractErrorMessage(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  void _filtrar(Object filtro) {
    _filtro = filtro;
    _pagina = 1;
    _cargar();
  }

  String _fecha(String valor) {
    final s = RegExp(r'([zZ]|[+-]\d\d:?\d\d)$').hasMatch(valor) ? valor : '${valor}Z';
    final f = DateTime.parse(s).toLocal();
    String dos(int n) => n.toString().padLeft(2, '0');
    return '${dos(f.day)}/${dos(f.month)}/${f.year} ${dos(f.hour)}:${dos(f.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      // Buscador
      Row(children: [
        Expanded(
          child: TextField(
            controller: _buscar,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => _filtrar(_filtro),
            style: GoogleFonts.inter(fontSize: 14),
            decoration: InputDecoration(
              hintText: 'Buscar por usuario o entidad...',
              isDense: true,
              filled: true,
              fillColor: Colors.white,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
              enabledBorder: const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: Color(0xFFDDDDDD))),
              focusedBorder: const OutlineInputBorder(borderRadius: BorderRadius.zero, borderSide: BorderSide(color: _noche)),
            ),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: _noche,
            shape: const RoundedRectangleBorder(),
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 17),
          ),
          onPressed: () => _filtrar(_filtro),
          child: Text('BUSCAR', style: GoogleFonts.inter(fontWeight: FontWeight.w800, letterSpacing: 0.5)),
        ),
      ]),
      const SizedBox(height: 18),
      // Filtros: todo el sistema, la plataforma o una tienda.
      Wrap(spacing: 8, runSpacing: 8, children: [
        _Filtro(texto: 'TODO EL SISTEMA', activo: _filtro == 'todas', onTap: () => _filtrar('todas')),
        _Filtro(texto: 'PLATAFORMA', activo: _filtro == 'plataforma', onTap: () => _filtrar('plataforma')),
        for (final t in _tiendas)
          _Filtro(
            texto: t['nombre'].toString().toUpperCase(),
            inicial: t['nombre'].toString().characters.first.toUpperCase(),
            color: colorMarca(t['color_marca'] as String?),
            activo: _filtro == t['id'],
            onTap: () => _filtrar(t['id'] as int),
          ),
      ]),
      const SizedBox(height: 20),
      if (_error != null)
        Container(
          padding: const EdgeInsets.all(12),
          margin: const EdgeInsets.only(bottom: 12),
          color: const Color(0xFFFDECEA),
          child: Text(_error!, style: const TextStyle(color: Color(0xFFB3261E))),
        ),
      // Tabla (se desliza a los lados, como en la web).
      Container(
        decoration: BoxDecoration(color: Colors.white, border: Border.all(color: _borde)),
        child: _cargando
            ? const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator()))
            : _items.isEmpty
                ? Padding(
                    padding: const EdgeInsets.all(30),
                    child: Center(child: Text('No hay registros.', style: GoogleFonts.inter(color: _gris))),
                  )
                : SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      _Fila(
                        cabecera: true,
                        celdas: const ['USUARIO', 'EMPRESA', 'ACCIÓN', 'ENTIDAD', 'FECHA', 'DISPOSITIVO', 'IP', 'DETALLE'],
                      ),
                      for (final i in _items)
                        _Fila(celdas: [
                          i,
                          i['empresa_nombre'] ?? 'Plataforma',
                          i['accion'],
                          i['entidad_id'] != null ? '${i['entidad_afectada']} #${i['entidad_numero'] ?? i['entidad_id']}' : i['entidad_afectada'],
                          _fecha(i['fecha'].toString()),
                          i['plataforma'] == 'web' ? 'Web' : i['plataforma'] == 'movil' ? 'Móvil' : (i['plataforma'] ?? '—'),
                          i['ip_address'] ?? '—',
                          i['detalle'] ?? '—',
                        ]),
                    ]),
                  ),
      ),
      const SizedBox(height: 18),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        _BotonPagina('ANTERIOR', _pagina > 1 && !_cargando ? () => setState(() => _pagina--) : null, _cargar),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Text('Pagina $_pagina de $_paginas', style: GoogleFonts.inter(fontSize: 13, color: const Color(0xFF777777))),
        ),
        _BotonPagina('SIGUIENTE', _pagina < _paginas && !_cargando ? () => setState(() => _pagina++) : null, _cargar),
      ]),
    ]);
  }
}

class _Filtro extends StatelessWidget {
  const _Filtro({required this.texto, required this.activo, required this.onTap, this.inicial, this.color});
  final String texto;
  final bool activo;
  final VoidCallback onTap;
  final String? inicial;
  final Color? color;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
          decoration: BoxDecoration(
            color: activo ? _noche : Colors.white,
            border: Border.all(color: activo ? _noche : const Color(0xFFDDDDDD)),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (inicial != null) ...[
              Container(
                width: 20,
                height: 20,
                alignment: Alignment.center,
                color: color,
                child: Text(inicial!, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800)),
              ),
              const SizedBox(width: 8),
            ],
            Text(texto,
                style: GoogleFonts.inter(fontSize: 12.5, fontWeight: FontWeight.w800, letterSpacing: 0.3,
                    color: activo ? Colors.white : _noche)),
          ]),
        ),
      );
}

const _anchos = [210.0, 110.0, 110.0, 150.0, 140.0, 100.0, 120.0, 280.0];

class _Fila extends StatelessWidget {
  const _Fila({required this.celdas, this.cabecera = false});
  final List<dynamic> celdas;
  final bool cabecera;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: _borde))),
      padding: EdgeInsets.symmetric(vertical: cabecera ? 16 : 14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (var n = 0; n < celdas.length; n++)
          Container(
            width: _anchos[n],
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: _celda(celdas[n], n),
          ),
      ]),
    );
  }

  Widget _celda(dynamic valor, int n) {
    if (cabecera) {
      return Text(valor.toString(),
          style: GoogleFonts.inter(fontSize: 11.5, fontWeight: FontWeight.w800, letterSpacing: 0.6, color: _gris));
    }
    // Usuario: nombre y correo.
    if (n == 0 && valor is Map) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(valor['usuario_nombre'].toString(), style: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w800, color: _noche)),
        Text(valor['usuario_email'].toString(), style: GoogleFonts.inter(fontSize: 12, color: _gris)),
      ]);
    }
    if (n == 2) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        color: const Color(0xFFF0F0F0),
        child: Text(valor.toString(), style: GoogleFonts.inter(fontSize: 10.5, fontWeight: FontWeight.w800, color: const Color(0xFF555555))),
      );
    }
    return Text(valor.toString(), style: GoogleFonts.inter(fontSize: 13.5, height: 1.35, color: _noche));
  }
}

class _BotonPagina extends StatelessWidget {
  const _BotonPagina(this.texto, this.cambiar, this.cargar);
  final String texto;
  final VoidCallback? cambiar;
  final Future<void> Function() cargar;

  @override
  Widget build(BuildContext context) => OutlinedButton(
        onPressed: cambiar == null
            ? null
            : () {
                cambiar!();
                cargar();
              },
        style: OutlinedButton.styleFrom(
          foregroundColor: _noche,
          side: const BorderSide(color: Color(0xFFDDDDDD)),
          shape: const RoundedRectangleBorder(),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        ),
        child: Text(texto, style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w800, letterSpacing: 0.4)),
      );
}
