import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../../models/producto_publico.dart';
import '../../widgets/product_card.dart';
import '../auth/auth_provider.dart';
import '../auth/login_requerido.dart';
import 'agregar_carrito_screen.dart';
import 'ar_foto_screen.dart';
import 'ar_tryon_screen.dart';
import 'catalogo_provider.dart';
import 'relacionados_provider.dart';
import 'reserva_form_screen.dart';

class ProductoDetalleScreen extends ConsumerStatefulWidget {
  const ProductoDetalleScreen({super.key, required this.productoId});

  final int productoId;

  @override
  ConsumerState<ProductoDetalleScreen> createState() => _ProductoDetalleScreenState();
}

class _ProductoDetalleScreenState extends ConsumerState<ProductoDetalleScreen> {
  late Future<ProductoPublico> _future;
  int _activeImage = 0;

  @override
  void initState() {
    super.initState();
    _future = ref.read(catalogoRepositoryProvider).getProducto(widget.productoId);
  }

  // CU09 requiere sesion iniciada (queda registrado quien probo cada
  // prenda para el dashboard de administracion) -- igual que en la web.
  // Con sesion, se elige entre ONLINE (camara en vivo) y VIRTUAL (subir
  // una foto), tambien igual que en la web.
  Future<void> _abrirProbadorAr(int productoId) async {
    // Sin sesion: avisa e invita a iniciar sesion / registrarse; al volver
    // logueado retoma esta misma accion (ver asegurarSesion).
    if (!await asegurarSesion(context, ref, accion: 'para probarte esta prenda con realidad aumentada')) return;
    if (!mounted) return;

    final modo = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.videocam_outlined, color: AppColors.brandDark),
              title: const Text('ONLINE', style: TextStyle(fontWeight: FontWeight.bold)),
              subtitle: const Text('Camara en vivo'),
              onTap: () => Navigator.of(ctx).pop('online'),
            ),
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined, color: AppColors.brandDark),
              title: const Text('VIRTUAL', style: TextStyle(fontWeight: FontWeight.bold)),
              subtitle: const Text('Subir o tomar una foto'),
              onTap: () => Navigator.of(ctx).pop('virtual'),
            ),
          ],
        ),
      ),
    );
    if (!mounted || modo == null) return;

    if (modo == 'online') {
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => ArTryonScreen(productoId: productoId)));
    } else {
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => ArFotoScreen(productoId: productoId)));
    }
  }

  // CU11 requiere sesion iniciada (el carrito queda ligado al cliente).
  Future<void> _abrirAgregarCarrito(int productoId, String productoNombre) async {
    if (!await asegurarSesion(context, ref, accion: 'para anadir productos a tu carrito')) return;
    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => AgregarCarritoScreen(productoId: productoId, productoNombre: productoNombre)),
    );
  }

  // CU10 requiere sesion iniciada (la reserva queda ligada al cliente que
  // la hizo, igual que CU09).
  Future<void> _abrirReserva(int productoId, String productoNombre) async {
    if (!await asegurarSesion(context, ref, accion: 'para reservar este producto')) return;
    if (!mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ReservaFormScreen(productoId: productoId, productoNombre: productoNombre)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('PRODUCTO')),
      body: FutureBuilder<ProductoPublico>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || !snapshot.hasData) {
            return const Center(child: Text('Producto no encontrado.'));
          }
          final p = snapshot.data!;
          final imagenes = p.imagenes.isEmpty ? <String>[] : p.imagenes;
          final auth = ref.watch(authProvider);

          return ListView(
            padding: EdgeInsets.only(bottom: 32 + MediaQuery.of(context).padding.bottom),
            children: [
              AspectRatio(
                aspectRatio: 1,
                child: imagenes.isEmpty
                    ? Container(color: AppColors.grayBorderLight)
                    : CachedNetworkImage(imageUrl: imagenes[_activeImage], fit: BoxFit.cover),
              ),
              if (imagenes.length > 1)
                SizedBox(
                  height: 64,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    itemCount: imagenes.length,
                    separatorBuilder: (_, _) => const SizedBox(width: 8),
                    itemBuilder: (context, i) => GestureDetector(
                      onTap: () => setState(() => _activeImage = i),
                      child: Container(
                        width: 56,
                        decoration: BoxDecoration(
                          border: Border.all(color: i == _activeImage ? AppColors.brandDark : AppColors.grayBorderLight, width: 2),
                        ),
                        child: CachedNetworkImage(imageUrl: imagenes[i], fit: BoxFit.cover),
                      ),
                    ),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                      decoration: BoxDecoration(border: Border.all(color: p.agotado ? AppColors.danger : AppColors.grayBorder)),
                      child: Text(
                        p.agotado ? 'AGOTADO' : 'EN STOCK',
                        style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: p.agotado ? AppColors.danger : AppColors.grayTextDark),
                      ),
                    ),
                    const SizedBox(height: 12),
                    EyebrowText(p.marcaNombre),
                    Text(
                      p.nombre,
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppColors.brandDark),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        if (p.tieneDescuento) ...[
                          Text(
                            '${p.precioOriginal!.toStringAsFixed(0)} Bs',
                            style: const TextStyle(color: AppColors.grayText, decoration: TextDecoration.lineThrough),
                          ),
                          const SizedBox(width: 8),
                        ],
                        Text(
                          '${p.precio.toStringAsFixed(0)} Bs',
                          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.brandDark),
                        ),
                      ],
                    ),
                    const Divider(height: 32),
                    Text(p.descripcion ?? 'Este producto no tiene una descripcion detallada todavia.'),
                    const Divider(height: 32),
                    if (auth.mostrarAccionCliente('CU13'))
                      ElevatedButton(
                        onPressed: p.agotado ? null : () => _abrirAgregarCarrito(p.id, p.nombre),
                        child: Text(p.agotado ? 'SIN STOCK' : 'ANADIR AL CARRITO'),
                      ),
                    if (p.hasPhotos && auth.mostrarAccionCliente('CU09')) ...[
                      const SizedBox(height: 10),
                      OutlinedButton.icon(
                        onPressed: () => _abrirProbadorAr(p.id),
                        icon: const Icon(Icons.camera_alt_outlined),
                        label: const Text('PROBARME CON REALIDAD AUMENTADA'),
                        style: OutlinedButton.styleFrom(
                          minimumSize: const Size.fromHeight(48),
                          foregroundColor: AppColors.brandDark,
                          side: const BorderSide(color: AppColors.brandDark),
                          shape: const RoundedRectangleBorder(),
                        ),
                      ),
                    ],
                    if (!p.agotado && auth.mostrarAccionCliente('CU10')) ...[
                      const SizedBox(height: 10),
                      OutlinedButton.icon(
                        onPressed: () => _abrirReserva(p.id, p.nombre),
                        icon: const Icon(Icons.calendar_today_outlined),
                        label: const Text('RESERVAR'),
                        style: OutlinedButton.styleFrom(
                          minimumSize: const Size.fromHeight(48),
                          foregroundColor: AppColors.brandDark,
                          side: const BorderSide(color: AppColors.brandDark),
                          shape: const RoundedRectangleBorder(),
                        ),
                      ),
                    ],
                    const SizedBox(height: 20),
                    Row(
                      children: [
                        const Text('Sucursales con stock: ', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                        Expanded(
                          child: Text(
                            p.sucursalesDisponibles.isEmpty ? 'Sin stock por el momento' : p.sucursalesDisponibles.join(', '),
                            style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        const Text('Categoria: ', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                        Text(p.categoriaNombre, style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        const Text('Temporada: ', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                        Text(p.temporadaNombre, style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark)),
                      ],
                    ),
                  ],
                ),
              ),
              _RelacionadosSection(productoId: p.id),
            ],
          );
        },
      ),
    );
  }
}

/// CU18 extendido: "Tambien te puede interesar" -- ver relacionados_provider.dart.
class _RelacionadosSection extends ConsumerWidget {
  const _RelacionadosSection({required this.productoId});

  final int productoId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final relacionados = ref.watch(relacionadosProvider(productoId)).valueOrNull ?? [];
    if (relacionados.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 32, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Divider(height: 1),
          const SizedBox(height: 24),
          const Text(
            'TAMBIEN TE PUEDE INTERESAR',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, fontStyle: FontStyle.italic, color: AppColors.brandDark),
          ),
          const SizedBox(height: 4),
          const Text(
            'Elegido segun lo que estas viendo -- con ayuda de IA.',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.grayText),
          ),
          const SizedBox(height: 16),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: relacionados.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 0.56,
            ),
            itemBuilder: (context, i) {
              final r = relacionados[i];
              return ProductCard(
                producto: r.producto,
                caption: r.razon,
                onTap: () => context.push('/producto/${r.producto.id}'),
              );
            },
          ),
        ],
      ),
    );
  }
}
