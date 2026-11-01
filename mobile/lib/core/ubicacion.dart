import 'package:geolocator/geolocator.dart';
import 'package:location/location.dart' as loc;

/// Ubicacion actual del telefono para "Usar mi ubicacion" (direcciones,
/// checkout, asistencia y sucursales):
/// 1. Pide el permiso de ubicacion (si lo nego para siempre, abre los
///    ajustes de la app para que lo active).
/// 2. Si el GPS esta apagado, muestra el dialogo del sistema "¿Activar la
///    ubicacion?" y, si acepta, se enciende solo (antes solo se avisaba).
/// 3. Lee la posicion.
/// Los errores se lanzan como texto para mostrarlos tal cual.
Future<Position> ubicacionActual({
  String sinPermiso = 'No diste permiso para usar tu ubicación.',
  String gpsApagado = 'No activaste la ubicación del teléfono.',
}) async {
  var permiso = await Geolocator.checkPermission();
  if (permiso == LocationPermission.denied) permiso = await Geolocator.requestPermission();
  if (permiso == LocationPermission.deniedForever) {
    await Geolocator.openAppSettings();
    throw '$sinPermiso Actívalo en los ajustes de la app y vuelve a intentar.';
  }
  if (permiso == LocationPermission.denied) throw sinPermiso;

  if (!await Geolocator.isLocationServiceEnabled()) {
    final encendido = await loc.Location().requestService();
    if (!encendido) throw gpsApagado;
  }

  return Geolocator.getCurrentPosition(
    locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 15)),
  );
}
