import 'dart:io' show Platform;

/// Cambiar a `false` para apuntar contra el backend LOCAL (docker compose
/// en la maquina, `10.0.2.2`/`localhost`) en vez del backend real de
/// produccion. En `true`, la app usa la base de datos real (Supabase, no
/// el Postgres local de docker) para todo -- catalogo, login, etc.
const bool usarBackendProduccion = true;

const String _backendProduccionUrl = 'https://arlani-boutiques-backend-30l6.onrender.com';
const String _frontendProduccionUrl = 'https://arlani-boutiques.vercel.app';

/// URL base de la API de FastAPI según la plataforma de ejecución.
///
/// - Emulador Android: 10.0.2.2 apunta al localhost de la máquina host.
/// - iOS simulator / desktop / web: localhost funciona directo.
/// - Dispositivo físico: reemplazar por la IP de la máquina en la red local
///   (si `usarBackendProduccion` esta en `false`).
String get apiBaseUrl {
  if (usarBackendProduccion) return '$_backendProduccionUrl/api/v1';
  if (Platform.isAndroid) {
    return 'http://10.0.2.2:8000/api/v1';
  }
  return 'http://localhost:8000/api/v1';
}

/// Probador CU09 (WebView -> pagina servida por el backend, ver
/// `backend/app/main.py::ar_embed`): SIEMPRE apunta al backend real de
/// produccion (https), nunca a `apiBaseUrl`. getUserMedia solo esta
/// disponible en un "contexto seguro" (https, o el literal "localhost");
/// `http://10.0.2.2:8000` (el backend local en el emulador) NO califica y
/// el navegador ni expone la API, asi que en dev el probador tampoco
/// funcionaria igual. Usar siempre el backend real evita ese problema en
/// cualquier dispositivo con internet, sin depender de tener el backend
/// corriendo en la maquina.
/// CU09 ahora requiere sesion iniciada (para registrar quien probo cada
/// prenda) -- el token va como query param porque esta pagina la carga el
/// WebView con `loadRequest` (una navegacion normal, no un fetch nuestro
/// donde podamos poner el header Authorization); el JS de la pagina lo lee
/// de `location.search` y lo manda el como header en su propio fetch a
/// `/ar-sesion`. Ver `ar_embed.py` del lado del backend.
String arEmbedUrl(int productoId, {String? token}) {
  final base = '$_backendProduccionUrl/ar-embed/$productoId';
  if (token == null || token.isEmpty) return base;
  return '$base?token=${Uri.encodeQueryComponent(token)}';
}

/// CU11 (checkout movil): pagina que renderiza los botones reales del SDK
/// de PayPal (igual que en la web) para embeber inline en el WebView del
/// checkout. Mismo motivo que `arEmbedUrl` para mandar el token por query
/// param en vez de un header: la carga un `loadRequest` normal.
String paypalEmbedUrl(String token) {
  return '$_backendProduccionUrl/paypal-embed?token=${Uri.encodeQueryComponent(token)}';
}

/// URL base del frontend Angular. Algunas imagenes de producto (las que
/// vienen de los assets estaticos del frontend, ej. "/img/productos/x.jpg")
/// son rutas RELATIVAS: en un navegador se resuelven solas contra el
/// dominio de la pagina, pero una app nativa no tiene "origen" propio y
/// necesita la URL absoluta. Ver `resolveImageUrl`.
///
/// En `usarBackendProduccion = true` siempre es el frontend real -- nunca
/// `10.0.2.2`, que solo existe dentro del emulador Android y no significa
/// nada en un dispositivo fisico (ahi las imagenes con ruta relativa
/// simplemente no cargaban).
String get webAssetsBaseUrl {
  if (usarBackendProduccion) return _frontendProduccionUrl;
  if (Platform.isAndroid) {
    return 'http://10.0.2.2:4200';
  }
  return 'http://localhost:4200';
}

/// Completa una URL de imagen relativa con `webAssetsBaseUrl`. Las URLs
/// absolutas (las que suben via CU05 a Supabase Storage) quedan intactas.
String resolveImageUrl(String url) {
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  return '$webAssetsBaseUrl$url';
}

/// Mismo Client ID "web" que usa el backend (`GOOGLE_CLIENT_ID` en
/// `backend/.env`) para validar el `id_token` de Google
/// (`id_token.verify_oauth2_token(..., audience=GOOGLE_CLIENT_ID)`). En
/// `google_sign_in` este valor va en `serverClientId`: hace que el token
/// que recibe la app tenga como `aud` este client id (no uno especifico de
/// Android), que es justo lo que el backend espera.
///
/// Para que el login con Google funcione en el emulador/dispositivo hace
/// falta, ademas, un cliente OAuth de tipo "Android" dado de alta en el
/// mismo proyecto de Google Cloud (paquete `com.atelieraranier.mobile_app`
/// + huella SHA-1 del keystore de debug/release) — sin eso Google devuelve
/// error 10 (DEVELOPER_ERROR) aunque el codigo este bien.
const googleServerClientId = '707417552911-t0qe58iv3q4kkdb7oj67qlrieqrifmg5.apps.googleusercontent.com';
