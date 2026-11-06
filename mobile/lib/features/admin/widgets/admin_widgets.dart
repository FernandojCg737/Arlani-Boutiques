import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme.dart';
import '../../auth/perfil_personal.dart' show marcaPersonalProvider;
import '../../portada/plataforma_data.dart' show colorMarca;

/// AppBar consistente para toda pantalla de admin: titulo mayuscula/negrita
/// (mismo estilo que ya define `AppBarTheme` en `theme.dart`), back
/// automatico (go_router lo provee al ser rutas empujadas, no tabs).
/// Pantalla de un CU del panel, con el color de la tienda (como --brand-dark
/// en la web): barra, botones, cargas y boton flotante.
class AdminScaffold extends ConsumerWidget {
  const AdminScaffold({super.key, required this.title, required this.body, this.actions, this.floatingActionButton});

  final String title;
  final Widget body;
  final List<Widget>? actions;
  final Widget? floatingActionButton;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final marca = ref.watch(marcaPersonalProvider).valueOrNull;
    final color = marca == null ? Theme.of(context).colorScheme.primary : colorMarca(marca['color_marca'] as String?);
    final base = Theme.of(context);
    return Theme(
      data: base.copyWith(
        colorScheme: base.colorScheme.copyWith(primary: color, secondary: color),
        appBarTheme: base.appBarTheme.copyWith(backgroundColor: color, foregroundColor: Colors.white),
        progressIndicatorTheme: ProgressIndicatorThemeData(color: color),
        floatingActionButtonTheme: FloatingActionButtonThemeData(backgroundColor: color, foregroundColor: Colors.white),
        filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(backgroundColor: color)),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(backgroundColor: color, foregroundColor: Colors.white),
        ),
      ),
      child: Scaffold(
        appBar: AppBar(title: Text(title), actions: actions),
        body: body,
        floatingActionButton: floatingActionButton,
      ),
    );
  }
}

/// Buscador con un pequeno debounce (300ms) para no disparar un request por
/// cada tecla — la web usa un submit explicito, esto es el equivalente
/// movil-idiomatico sin perder el criterio de busqueda del backend (`buscar`).
class AdminSearchField extends StatefulWidget {
  const AdminSearchField({super.key, required this.hintText, required this.onChanged});

  final String hintText;
  final ValueChanged<String> onChanged;

  @override
  State<AdminSearchField> createState() => _AdminSearchFieldState();
}

class _AdminSearchFieldState extends State<AdminSearchField> {
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: TextField(
        onChanged: (v) {
          _debounce?.cancel();
          _debounce = Timer(const Duration(milliseconds: 300), () => widget.onChanged(v));
        },
        decoration: InputDecoration(hintText: widget.hintText, prefixIcon: const Icon(Icons.search, size: 20)),
      ),
    );
  }
}

/// Badge de estado, ej. "ACTIVO"/"INACTIVO" o "ACTIVA"/"INACTIVA" — mismo
/// criterio visual que `.badge` en la web (borde fino, texto chico negrita).
class EstadoBadge extends StatelessWidget {
  const EstadoBadge({super.key, required this.estado, required this.activo});

  final String estado;
  final bool activo;

  @override
  Widget build(BuildContext context) {
    final color = activo ? AppColors.success : AppColors.danger;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(border: Border.all(color: color)),
      child: Text(
        estado.toUpperCase(),
        style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: color, letterSpacing: 0.3),
      ),
    );
  }
}

/// Badge neutro (metodo de registro, accion de bitacora, etc).
class NeutralBadge extends StatelessWidget {
  const NeutralBadge(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorder)),
      child: Text(
        text.toUpperCase(),
        style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: AppColors.grayTextDark, letterSpacing: 0.3),
      ),
    );
  }
}

/// Banner de error inline, igual al `.admin-error` de la web.
class AdminErrorBanner extends StatelessWidget {
  const AdminErrorBanner({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: AppColors.dangerBg, border: Border.all(color: AppColors.danger)),
      child: Text(message, style: const TextStyle(color: AppColors.danger, fontSize: 13)),
    );
  }
}

/// Confirmacion nativa equivalente a `confirm()` en la web, usada antes de
/// desactivar/eliminar.
Future<bool> confirmAdminAction(BuildContext context, {required String title, required String message}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
        TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirmar')),
      ],
    ),
  );
  return result ?? false;
}

/// Contenedor de fila para listas admin: card con borde fino, sin sombra.
class AdminCard extends StatelessWidget {
  const AdminCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(border: Border.all(color: AppColors.grayBorderLight)),
      child: child,
    );
  }
}

/// Fila etiqueta+valor chica, reutilizada en casi todas las cards admin.
class AdminInfoRow extends StatelessWidget {
  const AdminInfoRow(this.label, this.value, {super.key});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: RichText(
        text: TextSpan(
          style: const TextStyle(fontSize: 12, color: AppColors.grayTextDark),
          children: [
            TextSpan(text: '$label: ', style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.brandCharcoal)),
            TextSpan(text: value),
          ],
        ),
      ),
    );
  }
}

/// Bottom sheet estandar para formularios de crear/editar — scrollable,
/// con padding que respeta el teclado.
Future<T?> showAdminFormSheet<T>(BuildContext context, {required String title, required Widget Function(BuildContext) builder}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    builder: (context) {
      return Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: DraggableScrollableSheet(
          initialChildSize: 0.9,
          maxChildSize: 0.95,
          expand: false,
          builder: (context, scrollController) {
            return SafeArea(
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: AppColors.brandDark)),
                      IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
                    ],
                  ),
                  const SizedBox(height: 12),
                  builder(context),
                ],
              ),
            );
          },
        ),
      );
    },
  );
}

/// Texto de ayuda ("se genera contrasena temporal...") repetido en varios
/// formularios de creacion.
class AdminHintText extends StatelessWidget {
  const AdminHintText(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 12),
      child: Text(text, style: const TextStyle(fontSize: 12, color: AppColors.grayText, fontStyle: FontStyle.italic)),
    );
  }
}
