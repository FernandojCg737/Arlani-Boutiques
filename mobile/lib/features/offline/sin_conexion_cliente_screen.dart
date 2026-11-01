import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';

import '../auth/auth_provider.dart';
import '../portada/encabezado_plataforma.dart';
import '../portada/estilo_plataforma.dart';
import '../portada/plataforma_data.dart';
import '../storefront/catalogo_provider.dart';
import 'offline_modelos.dart';
import 'offline_servicio.dart';
import 'offline_widgets.dart';

/// Marco de las pantallas del cliente: encabezado de Arlani y "volver".
class MarcoClienteOffline extends ConsumerWidget {
  const MarcoClienteOffline({super.key, required this.volver, required this.alVolver, required this.children, this.abajo});
  final String volver;
  final VoidCallback alVolver;
  final List<Widget> children;
  final Widget? abajo;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final arriba = MediaQuery.paddingOf(context).top + EncabezadoPlataforma.alto;
    // Es parte del perfil: al cerrar sesion (o vencer) se sale de aqui.
    ref.listen<AuthState>(authProvider, (_, s) {
      if (!s.isAuthenticated) context.go('/');
    });
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(statusBarColor: Colors.transparent),
      child: Scaffold(
        backgroundColor: Plataforma.marfil,
        bottomNavigationBar: abajo,
        body: Stack(
          children: [
            SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(16, arriba + 24, 16, 40),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 1100),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: InkWell(
                          onTap: alVolver,
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Row(mainAxisSize: MainAxisSize.min, children: [
                              const Icon(Icons.arrow_back, size: 16, color: marcaOffline),
                              const SizedBox(width: 6),
                              Text(volver.toUpperCase(),
                                  style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.5, color: marcaOffline)),
                            ]),
                          ),
                        ),
                      ),
                      const SizedBox(height: 14),
                      ...children,
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: EncabezadoPlataforma(
                solido: true,
                pleno: true,
                onIrA: (s) => context.go(s == SeccionPortada.inicio ? '/' : '/?seccion=${s.name}'),
                onBuscar: (texto) {
                  ref.read(tiendaFiltrosProvider.notifier).setBusqueda(texto.trim());
                  context.go('/catalogo');
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Sin conexion" del cliente (`pages/sin-conexion` de la web): catalogo
/// guardado en el telefono para verlo, reservar o comprar sin internet. Todo
/// se envia solo a la tienda al volver la conexion.
class SinConexionClienteScreen extends ConsumerStatefulWidget {
  const SinConexionClienteScreen({super.key});

  @override
  ConsumerState<SinConexionClienteScreen> createState() => _SinConexionClienteScreenState();
}

class _SinConexionClienteScreenState extends ConsumerState<SinConexionClienteScreen> {
  final _resumenKey = GlobalKey();
  int? _tiendaId;
  final Map<int, int> _sucursalDe = {};
  final List<ItemLocal> _items = [];
  String _modo = 'reservar';
  DateTime _horario = mananaMediodia();
  String _entrega = 'retiro';
  int? _direccionId;
  String _formaPago = 'contra_entrega';
  int? _paypalId;
  bool _guardando = false;
  String _error = '';
  String _aviso = '';

  OfflineServicio get _s => ref.read(offlineProvider);

  Future<void> _descargar() async {
    setState(() => _error = '');
    try {
      await _s.revisarCatalogo(forzar: true);
    } catch (_) {
      if (mounted) setState(() => _error = 'No pudimos descargar el catálogo. Revisa tu conexión.');
    }
  }

  /// Lo que queda de una variante, descontando lo ya elegido.
  int _disponible(int sucursalId, ProductoLocal p, VarianteLocal v) {
    final usado = _items
        .where((i) => i.sucursalId == sucursalId && i.productoId == p.productoId && i.tallaId == v.tallaId && i.colorId == v.colorId)
        .fold(0, (t, i) => t + i.cantidad);
    return v.stock - usado;
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(offlineProvider);
    final c = s.catalogo;
    final tiendas = c?.tiendas ?? [];
    final tienda = tiendas.where((t) => t.empresaId == _tiendaId).firstOrNull ?? tiendas.firstOrNull;
    final sucursal = tienda == null
        ? null
        : (tienda.sucursales.where((x) => x.id == _sucursalDe[tienda.empresaId]).firstOrNull ?? tienda.sucursales.firstOrNull);
    // Solo las prendas con stock conocido en la sucursal elegida.
    final productos = [
      if (tienda != null && sucursal != null)
        for (final p in tienda.productos)
          if (p.variantes.any((v) => v.sucursalId == sucursal.id))
            ProductoLocal(
              productoId: p.productoId,
              nombre: p.nombre,
              precio: p.precio,
              imagenUrl: p.imagenUrl,
              categoria: p.categoria,
              variantes: [for (final v in p.variantes) if (v.sucursalId == sucursal.id) v],
            ),
    ];
    final ancho = MediaQuery.sizeOf(context).width;
    final dosColumnas = ancho >= 840;
    final total = _items.fold(0.0, (t, i) => t + i.precio * i.cantidad);

    final catalogo = tienda == null || sucursal == null
        ? const SizedBox.shrink()
        : CatalogoOffline(
            key: ValueKey('${tienda.empresaId}-${sucursal.id}'),
            productos: productos,
            disponible: (p, v) => _disponible(sucursal.id, p, v),
            alAgregar: (p, v, n) => setState(() {
              final ya = _items
                  .where((i) => i.sucursalId == sucursal.id && i.productoId == p.productoId && i.tallaId == v.tallaId && i.colorId == v.colorId)
                  .firstOrNull;
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
                  empresaId: tienda.empresaId,
                  empresaNombre: tienda.nombre,
                  sucursalId: sucursal.id,
                  sucursalNombre: sucursal.nombre,
                ));
              }
              _aviso = '';
            }),
          );

    return MarcoClienteOffline(
      volver: 'Mi cuenta',
      alVolver: () => context.canPop() ? context.pop() : context.go('/perfil'),
      abajo: !dosColumnas && _items.isNotEmpty ? _barraResumen(total) : null,
      children: [
        const CabeceraOffline(
          titulo: 'Sin conexión',
          texto: 'Guarda el catálogo en tu dispositivo para verlo sin internet, reservar o comprar. Todo se envía solo a la '
              'tienda cuando vuelvas a tener conexión; las compras se pagan en ese momento (o al recibirlas, si la tienda '
              'acepta contra entrega).',
        ),
        Align(
          alignment: Alignment.centerLeft,
          child: BotonOffline(
            s.descargandoCatalogo && c == null ? 'Descargando…' : (c != null ? 'Actualizar catálogo' : 'Descargar catálogo'),
            onPressed: !s.enLinea || s.descargandoCatalogo ? null : _descargar,
          ),
        ),
        const SizedBox(height: 14),
        const BarraConexion(),
        if (_error.isNotEmpty) AvisoOffline(_error, error: true),
        if (_aviso.isNotEmpty) AvisoOffline(_aviso),
        if (s.porPagar.isNotEmpty)
          AvisoOffline('Tienes ${s.porPagar.length} ${s.porPagar.length == 1 ? 'compra' : 'compras'} sin conexión por pagar.'),
        if (c == null)
          subOffline(s.enLinea
              ? 'Descargando el catálogo…'
              : 'Conéctate a internet una vez para descargar el catálogo y usarlo sin conexión.')
        else ...[
          Text.rich(
            TextSpan(children: [
              TextSpan(text: 'Catálogo guardado ${haceTiempo(c.descargadoEn)} (${fechaCorta(c.descargadoEn)}). '),
              if (s.enLinea && s.revisadoEn != null)
                TextSpan(
                  text: 'Stock al día · revisado a las ${fechaCorta(s.revisadoEn!).substring(11)}. ',
                  style: const TextStyle(color: marcaOffline, fontWeight: FontWeight.w600),
                ),
              if (!s.enLinea || DateTime.now().difference(c.descargadoEn).inHours >= 6)
                const TextSpan(
                  text: 'El stock puede haber cambiado: la tienda lo confirma al recibir tu reserva.',
                  style: TextStyle(color: ambarOffline, fontWeight: FontWeight.w600),
                ),
            ]),
            style: textoOffline(size: 12, color: const Color(0xFF777777)),
          ),
          const SizedBox(height: 12),
          if (tiendas.isEmpty)
            subOffline('Ninguna tienda trabaja sin conexión por ahora.')
          else ...[
            _pestanasTiendas(tiendas, tienda!),
            const SizedBox(height: 12),
            if (sucursal != null) ...[
              etiquetaOffline('Sucursal donde la recoges'),
              DropdownButtonFormField<int>(
                initialValue: sucursal.id,
                isExpanded: true,
                decoration: const InputDecoration(isDense: true, border: OutlineInputBorder(borderRadius: BorderRadius.zero)),
                items: [for (final x in tienda.sucursales) DropdownMenuItem(value: x.id, child: Text(x.nombre))],
                onChanged: (id) => setState(() => _sucursalDe[tienda.empresaId] = id!),
              ),
              const SizedBox(height: 12),
            ],
            if (dosColumnas)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 3, child: catalogo),
                  const SizedBox(width: 20),
                  Expanded(flex: 2, child: _resumen(c, total)),
                ],
              )
            else ...[
              catalogo,
              const SizedBox(height: 16),
              _resumen(c, total),
            ],
          ],
        ],
        tituloSeccionOffline('Mis reservas y compras sin conexión'),
        if (s.operaciones.isEmpty) subOffline('Todavía no hiciste reservas ni compras sin conexión.'),
        for (final o in s.operaciones)
          TarjetaOperacion(
            op: o,
            titulo: '${o.tipo == 'pedido' ? 'Compra' : 'Reserva'} · ${o.empresaNombre}',
            sub: '${o.sucursalNombre} · ${fechaCorta(DateTime.parse(o.registradaEn))}',
            estadoTexto: o.formaPago == 'paypal_guardado' && o.estado == 'pagada' ? 'Pago finalizado con éxito' : null,
            extra: [
              if (o.tipo == 'pedido' && (o.estado == 'por_pagar' || o.estado == 'sin_stock' || o.estado == 'en_espera'))
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton(
                    onPressed: () => context.push('/pagar-compras'),
                    child: Text(o.estado == 'por_pagar' ? 'Pagar ahora' : (o.estado == 'en_espera' ? 'Ver o cancelar' : 'Ver')),
                  ),
                ),
            ],
          ),
      ],
    );
  }

  Widget _pestanasTiendas(List<TiendaLocal> tiendas, TiendaLocal actual) => Container(
        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFFEEEEEE)))),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final t in tiendas)
                InkWell(
                  onTap: () => setState(() => _tiendaId = t.empresaId),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      border: Border(bottom: BorderSide(color: t == actual ? marcaOffline : Colors.transparent, width: 2)),
                    ),
                    child: Text(t.nombre.toUpperCase(),
                        style: textoOffline(size: 12, peso: FontWeight.w700, color: t == actual ? marcaOffline : const Color(0xFF999999))),
                  ),
                ),
            ],
          ),
        ),
      );

  String _prendas() {
    final n = _items.fold(0, (t, i) => t + i.cantidad);
    return '$n ${n == 1 ? 'prenda' : 'prendas'}';
  }

  /// En celular: barra fija con el total que lleva al resumen.
  Widget _barraResumen(double total) => SafeArea(
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 10, 12, 10),
          decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: Color(0xFFE5E2DF)))),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  '${_modo == 'reservar' ? 'Mi reserva' : 'Mi compra'} · ${_prendas()} · Bs ${bs(total)}',
                  style: textoOffline(peso: FontWeight.w700, color: marcaOffline),
                ),
              ),
              BotonOffline('Ver', onPressed: () {
                final ctx = _resumenKey.currentContext;
                if (ctx != null) Scrollable.ensureVisible(ctx, duration: const Duration(milliseconds: 350));
              }),
            ],
          ),
        ),
      );

  Widget _resumen(CatalogoCliente c, double total) {
    final grupos = <int, List<ItemLocal>>{};
    for (final i in _items) {
      (grupos[i.sucursalId!] ??= []).add(i);
    }
    final empresas = {for (final i in _items) i.empresaId};
    final elegidas = c.tiendas.where((t) => empresas.contains(t.empresaId)).toList();
    final aceptaContra = elegidas.isNotEmpty && elegidas.every((t) => t.aceptaContraEntrega);
    final aceptaPaypal = elegidas.isNotEmpty && elegidas.every((t) => t.aceptaPaypal);
    bool sirve(PaypalLocal pp) => pp.autorizada || empresas.every((e) => pp.tiendas.contains(e));
    // Forma de pago valida para lo elegido (si no, la otra).
    var forma = _formaPago;
    if (forma == 'contra_entrega' && !aceptaContra && aceptaPaypal) forma = 'paypal_guardado';
    if (forma == 'paypal_guardado' && !aceptaPaypal && aceptaContra) forma = 'contra_entrega';
    final paypal = c.paypals.where((x) => x.id == _paypalId).firstOrNull ??
        c.paypals.where(sirve).firstOrNull ??
        c.paypals.firstOrNull;
    final compra = _modo == 'comprar';

    final falta = <String>[
      if (_items.isEmpty) 'Elige prendas del catálogo.',
      if (compra && _entrega == 'envio' && _direccionId == null)
        c.direcciones.isEmpty ? 'Agrega una dirección en Mi cuenta (con conexión) para el envío.' : 'Elige la dirección de envío.',
      if (compra && _items.isNotEmpty && !aceptaPaypal && !aceptaContra)
        'Estas tiendas no reciben pagos sin conexión (PayPal o contra entrega).',
    ];

    Future<void> registrar() async {
      setState(() {
        _guardando = true;
        _error = '';
      });
      try {
        // Una operacion por sucursal: cada tienda recibe (y cobra) lo suyo.
        for (final g in grupos.values) {
          final conPaypal = compra && forma == 'paypal_guardado';
          await _s.registrar(
            tipo: compra ? 'pedido' : 'reserva',
            empresaNombre: g.first.empresaNombre!,
            sucursalId: g.first.sucursalId!,
            sucursalNombre: g.first.sucursalNombre!,
            items: g,
            horarioAtencion: compra ? null : _horario,
            entrega: compra ? _entrega : 'retiro',
            direccionId: compra && _entrega == 'envio' ? _direccionId : null,
            formaPago: compra ? forma : null,
            metodoPagoId: conPaypal ? paypal?.id : null,
            paypalCuenta: conPaypal ? paypal?.cuenta : null,
          );
        }
        setState(() {
          _items.clear();
          _aviso = compra
              ? (forma == 'paypal_guardado'
                  ? 'Pago enviado. Tu compra se cobra sola al volver internet (solo lo que siga con stock y al mismo precio o menor).'
                  : 'Compra guardada en tu teléfono: se envía sola a la tienda cuando tengas conexión.')
              : 'Reserva guardada en tu teléfono: se envía sola a la tienda cuando tengas conexión.';
        });
      } catch (_) {
        setState(() => _error = 'No se pudo guardar en el teléfono. Intenta de nuevo.');
      } finally {
        if (mounted) setState(() => _guardando = false);
      }
    }

    return Container(
      key: _resumenKey,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: Colors.white, border: Border.all(color: bordeOffline)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(
              child: OpcionOffline(
                  texto: 'Reservar', sub: 'pagas al recoger', activa: !compra, onTap: () => setState(() => _modo = 'reservar')),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: OpcionOffline(
                  texto: 'Comprar', sub: 'retiro o envío', activa: compra, onTap: () => setState(() => _modo = 'comprar')),
            ),
          ]),
          const SizedBox(height: 14),
          Text(compra ? 'Mi compra' : 'Mi reserva',
              style: GoogleFonts.playfairDisplay(fontSize: 20, fontWeight: FontWeight.w600, color: marcaOffline)),
          const SizedBox(height: 6),
          if (_items.isEmpty)
            subOffline('Elige prendas del catálogo.')
          else ...[
            for (final g in grupos.values) ...[
              const SizedBox(height: 6),
              Row(children: [
                Expanded(
                  child: Text('${g.first.empresaNombre} · ${g.first.sucursalNombre}',
                      style: textoOffline(size: 12.5, peso: FontWeight.w700)),
                ),
                Text('Bs ${bs(g.fold(0.0, (t, i) => t + i.precio * i.cantidad))}', style: textoOffline(size: 12.5)),
              ]),
              LineasElegidas(items: g, alQuitar: (i) => setState(() => _items.remove(i))),
            ],
            const SizedBox(height: 8),
            Text('Total: Bs ${bs(total)}', style: textoOffline(size: 15, peso: FontWeight.w800, color: marcaOffline)),
            if (grupos.length > 1) subOffline('Son ${grupos.length} tiendas o sucursales: cada una recibe su pedido.'),
            if (compra) subOffline('Precio conocido al descargar: se confirma al pagar.'),
          ],
          if (!compra)
            CampoFechaHora(etiqueta: 'La recojo hasta', valor: _horario, alCambiar: (d) => setState(() => _horario = d))
          else ...[
            etiquetaOffline('Entrega'),
            Wrap(spacing: 6, runSpacing: 6, children: [
              OpcionOffline(texto: 'Retiro en sucursal', activa: _entrega == 'retiro', onTap: () => setState(() => _entrega = 'retiro')),
              OpcionOffline(texto: 'Envío a domicilio', activa: _entrega == 'envio', onTap: () => setState(() => _entrega = 'envio')),
            ]),
            if (_entrega == 'envio' && c.direcciones.isNotEmpty) ...[
              etiquetaOffline('Dirección'),
              DropdownButtonFormField<int>(
                initialValue: _direccionId,
                isExpanded: true,
                hint: const Text('Elige una dirección'),
                decoration: const InputDecoration(isDense: true, border: OutlineInputBorder(borderRadius: BorderRadius.zero)),
                items: [
                  for (final d in c.direcciones)
                    DropdownMenuItem(value: d.id, child: Text('${d.alias}: ${d.direccion}', overflow: TextOverflow.ellipsis)),
                ],
                onChanged: (id) => setState(() => _direccionId = id),
              ),
            ],
            etiquetaOffline('¿Cómo pagas?'),
            Wrap(spacing: 6, runSpacing: 6, children: [
              if (aceptaContra || _items.isEmpty)
                OpcionOffline(
                  texto: 'Contra entrega',
                  sub: _entrega == 'envio' ? 'al recibirla' : 'al recogerla',
                  activa: forma == 'contra_entrega',
                  onTap: () => setState(() => _formaPago = 'contra_entrega'),
                ),
              if (aceptaPaypal || _items.isEmpty)
                OpcionOffline(
                  texto: 'Mi PayPal guardado',
                  sub: 'se cobra al sincronizar',
                  activa: forma == 'paypal_guardado',
                  onTap: () => setState(() => _formaPago = 'paypal_guardado'),
                ),
            ]),
            if (forma == 'paypal_guardado' && c.paypals.isNotEmpty) ...[
              etiquetaOffline('¿Con qué cuenta PayPal?'),
              Wrap(spacing: 6, runSpacing: 6, children: [
                for (final pp in c.paypals)
                  OpcionOffline(
                    texto: pp.cuenta ?? 'Cuenta PayPal',
                    sub: sirve(pp) ? 'se cobra sola al volver internet' : 'al volver internet confirmas el pago una vez y queda autorizada',
                    activa: pp.id == paypal?.id,
                    onTap: () => setState(() => _paypalId = pp.id),
                  ),
              ]),
              subOffline('Verás «Pago enviado». Al volver internet se cobra solo lo que siga con stock y al mismo precio (o menor); '
                  'lo demás no se te cobra.'),
            ] else if (forma == 'paypal_guardado')
              subOffline('Verás «Pago enviado». Al volver internet confirmas el pago con PayPal (solo esta vez) y desde ahí tus '
                  'compras sin conexión se cobran solas.'),
          ],
          if (falta.isNotEmpty && _items.isNotEmpty) faltaOffline(falta),
          const SizedBox(height: 14),
          BotonOffline(
            _guardando ? 'Guardando…' : (compra ? 'Comprar · Bs ${bs(total)}' : 'Reservar'),
            ancho: true,
            onPressed: _guardando || falta.isNotEmpty ? null : registrar,
          ),
        ],
      ),
    );
  }
}
