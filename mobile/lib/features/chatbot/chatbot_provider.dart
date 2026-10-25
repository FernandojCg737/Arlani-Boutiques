import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/chat_mensaje.dart';
import '../auth/auth_provider.dart';

class ChatbotRepository {
  ChatbotRepository(this._dio);

  final Dio _dio;

  Future<List<ChatMensaje>> misMensajes({bool universal = false}) async {
    final res = await _dio.get('/chatbot/mias', queryParameters: universal ? {'universal': true} : null);
    return (res.data as List<dynamic>).map((e) => ChatMensaje.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<ChatMensaje> enviar(String mensaje, {bool universal = false}) async {
    final res = await _dio.post('/chatbot/mensajes', data: {'mensaje': mensaje, if (universal) 'universal': true});
    return ChatMensaje.fromJson(res.data as Map<String, dynamic>);
  }

  /// Asistente universal sin sesion: el servidor no guarda la conversacion,
  /// asi que los ultimos mensajes van como historial (`enviarPublico` en la web).
  Future<ChatMensaje> enviarPublico(String mensaje, List<ChatMensaje> previos) async {
    final historial = previos
        .where((m) => m.id > 0 || m.remitente == 'cliente')
        .toList()
        .reversed
        .take(10)
        .toList()
        .reversed
        .map((m) => {'remitente': m.remitente, 'mensaje': m.mensaje})
        .toList();
    final res = await _dio.post('/chatbot/publico', data: {'mensaje': mensaje, 'historial': historial});
    return ChatMensaje(
      id: DateTime.now().millisecondsSinceEpoch,
      remitente: 'bot',
      mensaje: (res.data as Map<String, dynamic>)['mensaje'] as String,
      fecha: DateTime.now(),
    );
  }
}

final chatbotRepositoryProvider = Provider<ChatbotRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return ChatbotRepository(apiClient.dio);
});

class ChatbotState {
  const ChatbotState({this.mensajes = const [], this.enviando = false});

  final List<ChatMensaje> mensajes;
  final bool enviando;

  ChatbotState copyWith({List<ChatMensaje>? mensajes, bool? enviando}) {
    return ChatbotState(mensajes: mensajes ?? this.mensajes, enviando: enviando ?? this.enviando);
  }
}

/// CU19: historial de la conversacion con el asistente. El backend arma la
/// respuesta (motor de contexto real del catalogo/stock + Gemini); aca solo
/// se manda el mensaje y se muestra lo que vuelve -- igual que
/// `services/chatbot.ts` en la web.
class ChatbotNotifier extends StateNotifier<ChatbotState> {
  ChatbotNotifier(this._repo, {this.universal = false, this.publico = false}) : super(const ChatbotState());

  final ChatbotRepository _repo;

  /// El asistente de Arlani (portada y catalogo universal), con todas las tiendas.
  final bool universal;

  /// Sin sesion de cliente: la conversacion vive solo en el telefono.
  final bool publico;

  Future<void> cargar() async {
    if (publico) return;
    try {
      state = state.copyWith(mensajes: await _repo.misMensajes(universal: universal));
    } catch (_) {
      state = state.copyWith(mensajes: const []);
    }
  }

  void limpiarLocal() {
    state = const ChatbotState();
  }

  /// Devuelve el mensaje del bot (para que la pantalla lo lea en voz alta
  /// si corresponde) o null si fallo.
  Future<ChatMensaje?> enviar(String texto) async {
    final limpio = texto.trim();
    if (limpio.isEmpty) return null;

    final optimista = ChatMensaje(
      id: -DateTime.now().millisecondsSinceEpoch,
      remitente: 'cliente',
      mensaje: limpio,
      fecha: DateTime.now(),
    );
    state = state.copyWith(mensajes: [...state.mensajes, optimista], enviando: true);

    try {
      final respuesta = publico
          ? await _repo.enviarPublico(limpio, state.mensajes.sublist(0, state.mensajes.length - 1))
          : await _repo.enviar(limpio, universal: universal);
      state = state.copyWith(mensajes: [...state.mensajes, respuesta], enviando: false);
      return respuesta;
    } catch (_) {
      final fallback = ChatMensaje(
        id: -DateTime.now().millisecondsSinceEpoch,
        remitente: 'bot',
        mensaje: 'No pudimos conectar con el asistente. Intenta de nuevo en un momento.',
        fecha: DateTime.now(),
      );
      state = state.copyWith(mensajes: [...state.mensajes, fallback], enviando: false);
      return null;
    }
  }
}

final chatbotProvider = StateNotifierProvider<ChatbotNotifier, ChatbotState>((ref) {
  final repo = ref.watch(chatbotRepositoryProvider);
  return ChatbotNotifier(repo);
});


/// Chat universal de la portada: publico para visitantes, guardado para clientes.
final chatbotUniversalProvider = StateNotifierProvider<ChatbotNotifier, ChatbotState>((ref) {
  final repo = ref.watch(chatbotRepositoryProvider);
  final esCliente = ref.watch(authProvider.select((a) => a.usuario?.isCliente ?? false));
  return ChatbotNotifier(repo, universal: true, publico: !esCliente);
});
