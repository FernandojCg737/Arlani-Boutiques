import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../admin/widgets/admin_widgets.dart';
import 'offline_modelos.dart';
import 'offline_servicio.dart';
import 'offline_widgets.dart';

/// CU23 "Trabajar sin conexion" (`pages/admin/sin-conexion` de la web): CU11
/// consultar el catalogo descargado de la sucursal, CU12 registrar ventas de
/// contado y reservas sin internet (se sincronizan solas) y CU13 ver esas
/// operaciones y su estado. Los conflictos se resuelven en la web.
class SinConexionPersonalScreen extends ConsumerStatefulWidget {
  const SinConexionPersonalScreen({super.key});

  @override
  ConsumerState<SinConexionPersonalScreen> createState() => _SinConexionPersonalScreenState();
}

class _SinConexionPersonalScreenState extends ConsumerState<SinConexionPersonalScreen> {
  List<SucursalLocal> _sucursales = [];
  int? _sucursalId;
  PaquetePersonal? _paquete;
  DateTime? _vistaDescarga;
  String _vista = 'catalogo';
  String _buscar = '';
  final List<ItemLocal> _items = [];
  int? _clienteId;
  String _buscarCliente = '';
  final _facturaNombre = TextEditingController();
  final _facturaNit = TextEditingController();
  DateTime _horario = mananaMediodia();
  bool _descargando = false;
  bool _guardando = false;
  String _error = '';
  String _aviso = '';

  OfflineServicio get _s => ref.read(offlineProvider);

  @override
  void initState() {
    super.initState();
    _iniciar();
  }

  @override
  void dispose() {
    _facturaNombre.dispose();
    _facturaNit.dispose();
    super.dispose();
  }

  Future<void> _iniciar() async {
    final lista = await _s.sucursalesPersonal();
    if (!mounted) return;
    setState(() => _sucursales = lista);
    if (lista.isNotEmpty) await _elegirSucursal(lista.first.id);
  }

  Future<void> _elegirSucursal(int id) async {
    final pq = await _s.paquetePersonal(id);
    if (!mounted) return;
    setState(() {
      if (_sucursalId != id) _items.clear();
      _sucursalId = id;
      _paquete = pq;
      _vistaDescarga = _s.ultimaDescargaPersonal;
    });
  }

  Future<void> _descargar() async {
    final id = _sucursalId;
    if (id == null) return;
    setState(() {
      _descargando = true;
      _error = '';
    });
    try {
      await _s.descargarPersonal(sucursalId: id);
      await _elegirSucursal(id);
    } catch (_) {
      setState(() => _error = 'No pudimos descargar los datos de la sucursal. Revisa tu conexión.');
    } finally {
      if (mounted) setState(() => _descargando = false);
    }
  }

  int _disponible(ProductoLocal p, VarianteLocal v) =>
      v.stock -
      _items
          .where((i) => i.productoId == p.productoId && i.tallaId == v.tallaId && i.colorId == v.colorId)
          .fold(0, (t, i) => t + i.cantidad);

  Future<void> _registrar() async {
    final pq = _paquete!;
    final venta = _vista == 'venta';
    final cliente = pq.clientes.where((c) => c.id == _clienteId).firstOrNull;
    setState(() {
      _guardando = true;
      _error = '';
    });
    try {
      await _s.registrar(
        tipo: venta ? 'venta' : 'reserva',
        empresaNombre: pq.empresaNombre,
        sucursalId: pq.sucursal.id,
        sucursalNombre: pq.sucursal.nombre,
        items: List.of(_items),
        clienteId: cliente?.id,
        clienteNombre: cliente?.nombre,
        facturaNombre: venta && cliente == null && _facturaNombre.text.trim().isNotEmpty ? _facturaNombre.text.trim() : null,
        facturaNit: venta && _facturaNit.text.trim().isNotEmpty ? _facturaNit.text.trim() : null,
        horarioAtencion: venta ? null : _horario,
      );
      setState(() {
        _items.clear();
        _clienteId = null;
        _buscarCliente = '';
        _facturaNombre.clear();
        _facturaNit.clear();
        _aviso = '${venta ? 'Venta' : 'Reserva'} guardada en este dispositivo: se envía sola al volver la conexión.';
      });
    } catch (_) {
      setState(() => _error = 'No se pudo guardar en el dispositivo. Intenta de nuevo.');
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(offlineProvider);
    // Llego una descarga automatica: se muestra el catalogo nuevo (la venta en curso no se toca).
    if (s.ultimaDescargaPersonal != _vistaDescarga && _sucursalId != null) {
      _vistaDescarga = s.ultimaDescargaPersonal;
      WidgetsBinding.instance.addPostFrameCallback((_) => _elegirSucursal(_sucursalId!));
    }
    final pq = _paquete;
    final contador = s.pendientes + s.conflictos;

    return AdminScaffold(
      title: 'Trabajar sin conexión',
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
        children: [
          const CabeceraOffline(
            eyebrow: 'P4 · CU23 · Offline',
            titulo: 'Trabajar sin conexión',
            texto: 'Mientras tienes internet, los datos de tu sucursal se descargan solos cada 3 minutos. Si se corta, entra '
                'aquí y sigue vendiendo al contado y reservando: todo queda guardado en este dispositivo y, al volver la '
                'conexión, primero se envía y después se vuelve a descargar el catálogo.',
          ),
          const BarraConexion(personal: true),
          if (s.planOffline == false)
            const AvisoOffline('El plan de tu tienda no incluye la operación sin conexión (solo Básico y Profesional).', error: true),
          if (_error.isNotEmpty) AvisoOffline(_error, error: true),
          if (_aviso.isNotEmpty) AvisoOffline(_aviso),
          etiquetaOffline('Sucursal'),
          DropdownButtonFormField<int>(
            key: ValueKey(_sucursales.length),
            initialValue: _sucursalId,
            isExpanded: true,
            hint: const Text('Sin sucursales descargadas'),
            decoration: const InputDecoration(isDense: true, border: OutlineInputBorder(borderRadius: BorderRadius.zero)),
            items: [for (final x in _sucursales) DropdownMenuItem(value: x.id, child: Text(x.nombre))],
            onChanged: (id) => _elegirSucursal(id!),
          ),
          const SizedBox(height: 8),
          if (pq != null) ...[
            Text('Datos descargados ${haceTiempo(pq.descargadoEn)} (${fechaCorta(pq.descargadoEn)}) · '
                '${pq.productos.length} prendas · ${pq.clientes.length} clientes', style: textoOffline(size: 12.5)),
            subOffline(s.descargandoPersonal ? 'Actualizando ahora…' : 'Se actualiza solo cada 3 minutos con conexión.'),
            if (!s.enLinea || DateTime.now().difference(pq.descargadoEn).inHours >= 6)
              Text('El stock que ves es el conocido al descargar: puede estar desactualizado. Se confirma al sincronizar.',
                  style: textoOffline(size: 12, peso: FontWeight.w600, color: ambarOffline)),
          ] else
            subOffline('Todavía no descargaste los datos de esta sucursal en este dispositivo.'),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerLeft,
            child: BotonOffline(
              _descargando ? 'Descargando…' : (pq != null ? 'Actualizar datos' : 'Descargar datos'),
              onPressed: !s.enLinea || _descargando || _sucursalId == null ? null : _descargar,
            ),
          ),
          const SizedBox(height: 16),
          _pestanas(contador),
          const SizedBox(height: 14),
          ...switch (_vista) {
            'catalogo' => _catalogo(pq),
            'operaciones' => _operaciones(s),
            _ => _formulario(pq),
          },
        ],
      ),
    );
  }

  Widget _pestanas(int contador) {
    Widget tab(String id, String texto) => InkWell(
          onTap: () => setState(() {
            _vista = id;
            _aviso = '';
          }),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: _vista == id ? marcaOffline : Colors.transparent, width: 2)),
            ),
            child: Row(children: [
              Text(texto.toUpperCase(),
                  style: textoOffline(size: 12, peso: FontWeight.w700, color: _vista == id ? marcaOffline : const Color(0xFF999999))),
              if (id == 'operaciones' && contador > 0) ...[
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  color: ambarOffline,
                  child: Text('$contador', style: textoOffline(size: 11, peso: FontWeight.w700, color: Colors.white)),
                ),
              ],
            ]),
          ),
        );
    return Container(
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE)))),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(children: [
          tab('catalogo', 'Catálogo descargado'),
          tab('venta', 'Venta de contado'),
          tab('reserva', 'Reserva'),
          tab('operaciones', 'Operaciones del dispositivo'),
        ]),
      ),
    );
  }

  List<Widget> _catalogo(PaquetePersonal? pq) {
    if (pq == null) return [subOffline('Descarga los datos de la sucursal para consultarlos sin conexión.')];
    final q = _buscar.trim().toLowerCase();
    final lista = pq.productos
        .where((p) => q.isEmpty || p.nombre.toLowerCase().contains(q) || (p.categoria ?? '').toLowerCase().contains(q))
        .toList();
    return [
      TextField(
        decoration: const InputDecoration(
          hintText: 'Buscar prenda o categoría…',
          prefixIcon: Icon(Icons.search, size: 20),
          isDense: true,
          border: OutlineInputBorder(borderRadius: BorderRadius.zero),
        ),
        onChanged: (v) => setState(() => _buscar = v),
      ),
      const SizedBox(height: 10),
      if (lista.isEmpty) subOffline('Ninguna prenda coincide.'),
      for (final p in lista)
        Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: Colors.white, border: Border.all(color: const Color(0xFFEEEEEE))),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(width: 56, height: 70, child: FotoPrenda(url: p.imagenUrl, nombre: p.nombre)),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(child: Text(p.nombre, style: textoOffline(peso: FontWeight.w700))),
                      Text('Bs ${bs(p.precio)}', style: textoOffline(peso: FontWeight.w600)),
                    ]),
                    subOffline('${p.categoria ?? 'Sin categoría'} · ${p.stockTotal} en total'),
                    const SizedBox(height: 6),
                    Wrap(spacing: 6, runSpacing: 4, children: [
                      for (final v in p.variantes)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          color: v.stock < 1 ? const Color(0xFFFDECEA) : const Color(0xFFF1F1F1),
                          child: Text('${v.tallaCodigo} · ${v.colorNombre}: ${v.stock}',
                              style: textoOffline(size: 11.5, color: v.stock < 1 ? const Color(0xFFB3261E) : const Color(0xFF555555))),
                        ),
                    ]),
                  ],
                ),
              ),
            ],
          ),
        ),
    ];
  }

  List<Widget> _operaciones(OfflineServicio s) => [
        if (s.operaciones.isEmpty) subOffline('Este dispositivo no tiene operaciones sin conexión.'),
        for (final o in s.operaciones)
          TarjetaOperacion(
            op: o,
            titulo: '${o.tipo == 'venta' ? 'Venta de contado' : 'Reserva'} · Bs ${bs(o.total)}',
            sub: '${o.sucursalNombre} · ${fechaCorta(DateTime.parse(o.registradaEn))} · ID ${o.uuid.substring(0, 8)}'
                '${o.intentos > 0 ? ' · ${o.intentos} ${o.intentos == 1 ? 'envío' : 'envíos'}' : ''}',
            extra: [
              if (o.clienteNombre != null) subOffline('Cliente: ${o.clienteNombre}'),
              if (o.ventaId != null) subOffline('Venta #${o.ventaNumero ?? o.ventaId}'),
              if (o.reservaId != null) subOffline('Reserva #${o.reservaNumero ?? o.reservaId}'),
              if (o.estado == 'conflicto') subOffline('Lo resuelve el encargado o el administrador desde la web.'),
            ],
          ),
        if (s.ultimoError.isNotEmpty) AvisoOffline(s.ultimoError, error: true),
        if (s.registro.isNotEmpty) ...[
          tituloSeccionOffline('Historial de sincronización'),
          for (final r in s.registro)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 8),
              decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE)))),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(fechaCorta(r.fecha), style: textoOffline(size: 12, peso: FontWeight.w700)),
                Text('${r.enviadas} enviadas · ${r.confirmadas} confirmadas · ${r.conflictos} en conflicto · '
                    '${r.rechazadas} rechazadas · ${r.errores} por reintentar', style: textoOffline(size: 12)),
                subOffline(r.detalle),
              ]),
            ),
        ],
      ];

  List<Widget> _formulario(PaquetePersonal? pq) {
    if (pq == null) return [subOffline('Primero descarga los datos de la sucursal (necesitas conexión una vez).')];
    final venta = _vista == 'venta';
    final total = _items.fold(0.0, (t, i) => t + i.precio * i.cantidad);
    final falta = [
      if (_items.isEmpty) 'Agrega al menos una prenda.',
      if (!venta && _clienteId == null) 'Elige el cliente de la reserva.',
    ];
    final q = _buscarCliente.trim().toLowerCase();
    final sugeridos = pq.clientes
        .where((c) => c.nombre.toLowerCase().contains(q) || c.email.toLowerCase().contains(q))
        .take(6)
        .toList();

    final catalogo = CatalogoOffline(
      key: ValueKey('${pq.sucursal.id}-$_vista'),
      productos: pq.productos,
      disponible: _disponible,
      bloquearSinStock: true,
      alAgregar: (p, v, n) => setState(() {
        final ya = _items.where((i) => i.productoId == p.productoId && i.tallaId == v.tallaId && i.colorId == v.colorId).firstOrNull;
        if (ya != null) {
          ya.cantidad += n;
        } else {
          _items.add(ItemLocal(
            productoId: p.productoId,
            tallaId: v.tallaId,
            colorId: v.colorId,
            cantidad: n,
            precio: p.precio,
            productoNombre: p.nombre,
            talla: v.tallaCodigo,
            color: v.colorNombre,
          ));
        }
        _aviso = '';
      }),
    );

    final resumen = Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: bordeOffline)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(venta ? 'Venta de contado (efectivo)' : 'Reserva',
              style: textoOffline(size: 17, peso: FontWeight.w700, color: marcaOffline)),
          subOffline('${pq.sucursal.nombre} · ${pq.empresaNombre}'),
          const SizedBox(height: 6),
          if (_items.isEmpty)
            subOffline('Elige las prendas en el catálogo.')
          else ...[
            LineasElegidas(items: _items, alQuitar: (i) => setState(() => _items.remove(i))),
            const SizedBox(height: 8),
            Text('Total: Bs ${bs(total)}', style: textoOffline(size: 15, peso: FontWeight.w800, color: marcaOffline)),
          ],
          etiquetaOffline(venta ? 'Cliente con cuenta (opcional)' : 'Cliente registrado'),
          if (_clienteId != null)
            Row(children: [
              Expanded(child: Text(_buscarCliente, style: textoOffline(peso: FontWeight.w600))),
              TextButton(onPressed: () => setState(() {
                _clienteId = null;
                _buscarCliente = '';
              }), child: const Text('cambiar')),
            ])
          else ...[
            TextField(
              decoration: const InputDecoration(
                  hintText: 'Nombre o correo', isDense: true, border: OutlineInputBorder(borderRadius: BorderRadius.zero)),
              onChanged: (v) => setState(() => _buscarCliente = v),
            ),
            if (q.isNotEmpty)
              if (sugeridos.isEmpty)
                subOffline('Ningún cliente descargado coincide.')
              else
                for (final c in sugeridos)
                  ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(c.nombre),
                    subtitle: Text(c.email),
                    onTap: () => setState(() {
                      _clienteId = c.id;
                      _buscarCliente = c.nombre;
                    }),
                  ),
          ],
          if (venta) ...[
            if (_clienteId == null) ...[
              etiquetaOffline('Nombre para la factura (sin cuenta)'),
              TextField(
                controller: _facturaNombre,
                maxLength: 150,
                decoration: const InputDecoration(isDense: true, counterText: '', border: OutlineInputBorder(borderRadius: BorderRadius.zero)),
              ),
            ],
            etiquetaOffline('NIT o CI (opcional)'),
            TextField(
              controller: _facturaNit,
              maxLength: 20,
              decoration: const InputDecoration(isDense: true, counterText: '', border: OutlineInputBorder(borderRadius: BorderRadius.zero)),
            ),
            subOffline('Sin conexión solo se cobra al contado, en efectivo.'),
          ] else
            CampoFechaHora(etiqueta: 'La recoge hasta', valor: _horario, alCambiar: (d) => setState(() => _horario = d)),
          if (falta.isNotEmpty) faltaOffline(falta),
          const SizedBox(height: 14),
          BotonOffline(
            _guardando ? 'Guardando…' : (venta ? 'Registrar venta · Bs ${bs(total)}' : 'Registrar reserva'),
            ancho: true,
            onPressed: _guardando || falta.isNotEmpty ? null : _registrar,
          ),
        ],
      ),
    );

    if (MediaQuery.sizeOf(context).width >= 840) {
      return [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(flex: 3, child: catalogo),
          const SizedBox(width: 20),
          Expanded(flex: 2, child: resumen),
        ]),
      ];
    }
    return [catalogo, const SizedBox(height: 16), resumen];
  }
}
