/// Menu del SuperAdministrador (`superadmin-menu.ts` de la web): dos
/// parciales, cada uno con sus paquetes y casos de uso.
///
/// Los CUs del 1er parcial que se mejoraron en el 2do ya no estan en el 1ro:
/// quedan en el 2do con su numero nuevo (`antes`) y en el 1ro solo la
/// referencia en `movidos`.
library;

class CasoMenu {
  const CasoMenu(this.codigo, this.nombre, {this.ruta, this.antes, this.porEmpresa = false, this.descripcion});

  final String codigo;
  final String nombre;
  // Pantalla donde opera en la web (/superadmin/<ruta>).
  final String? ruta;
  final String? antes;
  final bool porEmpresa;
  final String? descripcion;
}

class MovidoMenu {
  const MovidoMenu(this.de, this.a, this.nombre);
  final String de;
  final String a;
  final String nombre;
}

class PaqueteMenu {
  const PaqueteMenu(this.codigo, this.nombre, this.casos, {this.movidos = const []});
  final String codigo;
  final String nombre;
  final List<CasoMenu> casos;
  final List<MovidoMenu> movidos;
}

class ParcialMenu {
  const ParcialMenu(this.id, this.nombre, this.paquetes);
  final String id;
  final String nombre;
  final List<PaqueteMenu> paquetes;
}

const parcialesSuperadmin = [
  ParcialMenu('p1', '1er Parcial', [
    PaqueteMenu('P1', 'Gestión de Accesos y Seguridad', [], movidos: [
      MovidoMenu('CU01', 'CU01', 'Gestionar inicio y cierre de sesión'),
      MovidoMenu('CU02', 'CU02', 'Administrar usuarios, roles y permisos'),
      MovidoMenu('CU17', 'CU08', 'Auditar operaciones (bitácora)'),
    ]),
    PaqueteMenu('P2', 'Gestión de Clientes y Sucursales', [
      CasoMenu('CU03', 'Registrar y Administrar Clientes', ruta: 'clientes', porEmpresa: true),
      CasoMenu('CU15', 'Actualizar Perfil de Usuario', ruta: 'perfil'),
    ], movidos: [
      MovidoMenu('CU04', 'CU03', 'Administrar ciudades y sucursales'),
    ]),
    PaqueteMenu('P3', 'Gestión de Catálogo e Inventario', [
      CasoMenu('CU06', 'Administrar Proveedores', ruta: 'proveedores', porEmpresa: true),
      CasoMenu('CU07', 'Configurar Temporadas y Colecciones', ruta: 'temporadas', porEmpresa: true),
    ], movidos: [
      MovidoMenu('CU05', 'CU04', 'Administrar catálogo de productos'),
      MovidoMenu('CU08', 'CU04', 'Consultar catálogo y disponibilidad'),
      MovidoMenu('CU12', 'CU04', 'Controlar inventario por sucursal'),
    ]),
    PaqueteMenu('P4', 'Gestión de Reservas y Ventas', [
      CasoMenu('CU09', 'Visualizar Prenda con Realidad Aumentada', ruta: 'ar-uso', porEmpresa: true),
      CasoMenu('CU13', 'Administrar Carrito de Compras', ruta: 'carritos', porEmpresa: true),
    ], movidos: [
      MovidoMenu('CU10', 'CU05', 'Gestión de reservas'),
      MovidoMenu('CU11', 'CU06', 'Gestión de ventas'),
    ]),
    PaqueteMenu('P5', 'Gestión de Experiencia y Analítica', [
      CasoMenu('CU14', 'Enviar Notificaciones', ruta: 'notificaciones', porEmpresa: true),
      CasoMenu('CU19', 'Atender Cliente con Chatbot', ruta: 'chatbot', porEmpresa: true),
      CasoMenu('CU20', 'Reputación y Calificaciones', ruta: 'calificaciones', porEmpresa: true),
    ], movidos: [
      MovidoMenu('CU16', 'CU07', 'Gestión de reportes y dashboards'),
      MovidoMenu('CU18', 'CU18', 'Recomendar prendas por IA'),
    ]),
  ]),
  ParcialMenu('p2', '2do Parcial', [
    PaqueteMenu('P1', 'Seguridad y Acceso', [
      CasoMenu('CU01', 'Gestionar inicio y cierre de sesión', ruta: 'sesiones', antes: 'CU01'),
      CasoMenu('CU02', 'Administrar usuarios, roles y permisos', ruta: 'usuarios', antes: 'CU02'),
      CasoMenu('CU08', 'Auditar operaciones (bitácora)', ruta: 'bitacora', antes: 'CU17',
          descripcion: 'Registro de bitácora: alta de usuarios y demás operaciones auditadas del sistema.'),
      CasoMenu('CU21', 'Gestionar backups y restauración', ruta: 'backups',
          descripcion: 'Copias de seguridad manuales o programadas de una tienda o del sistema completo, con imágenes, y '
              'restauración por secciones que combina con lo actual sin borrar nada.'),
    ]),
    PaqueteMenu('P2', 'Plataforma SaaS', [
      CasoMenu('CU09', 'Gestionar empresas (tenants)', ruta: 'empresas'),
      CasoMenu('CU10', 'Gestionar y verificar planes, suscripciones y límites', ruta: 'planes'),
    ]),
    PaqueteMenu('P3', 'Operación de Tiendas', [
      CasoMenu('CU03', 'Administrar ciudades y sucursales', ruta: 'sucursales', antes: 'CU04', porEmpresa: true),
      CasoMenu('CU04', 'Catálogo e inventario', ruta: 'productos', antes: 'CU05 · CU08 · CU12', porEmpresa: true),
      CasoMenu('CU05', 'Gestionar reservas (online y offline)', ruta: 'reservas', antes: 'CU10', porEmpresa: true),
      CasoMenu('CU06', 'Gestionar ventas (online y offline)', ruta: 'ventas', antes: 'CU11', porEmpresa: true),
      CasoMenu('CU19', 'Gestionar métodos de pago', ruta: 'metodos-pago', porEmpresa: true),
      CasoMenu('CU15', 'Gestionar cambio de prendas', ruta: 'cambios', porEmpresa: true),
      CasoMenu('CU16', 'Arqueo y cierre de caja', ruta: 'caja', porEmpresa: true),
      CasoMenu('CU22', 'Gestionar live commerce', ruta: 'live',
          descripcion: 'Los lives en curso de todas las tiendas: entrar a verlos, moderar y cortarlos si incumplen los '
              'términos y condiciones.'),
    ]),
    PaqueteMenu('P4', 'Offline y Sincronización', [
      CasoMenu('CU11', 'Descargar y consultar catálogo offline', ruta: 'descargas-offline', porEmpresa: true),
      CasoMenu('CU12', 'Sincronizar operaciones pendientes', ruta: 'sincronizacion-offline', porEmpresa: true),
      CasoMenu('CU13', 'Consultar operaciones locales y su estado', ruta: 'operaciones-offline', porEmpresa: true),
      CasoMenu('CU14', 'Gestionar conflictos de sincronización', ruta: 'conflictos', porEmpresa: true),
    ]),
    PaqueteMenu('P5', 'Inteligencia y Reportes', [
      CasoMenu('CU07', 'Gestionar reportes y dashboards', ruta: 'reportes', antes: 'CU16', porEmpresa: true),
      CasoMenu('CU17', 'Solicitar y exportar reporte generativo (texto o voz)', ruta: 'reporte-voz', porEmpresa: true),
      CasoMenu('CU18', 'Gestionar modelos de ML', ruta: 'modelos-ml', antes: 'CU18'),
      CasoMenu('CU20', 'Gestionar reportes de la plataforma (SaaS)', ruta: 'reportes-saas'),
    ]),
  ]),
];

/// Donde esta un CU (parcial, paquete y caso).
class UbicacionCaso {
  const UbicacionCaso(this.parcial, this.paquete, this.caso);
  final ParcialMenu parcial;
  final PaqueteMenu paquete;
  final CasoMenu caso;
}

UbicacionCaso? buscarCaso(String parcialId, String codigo) {
  final parcial = parcialesSuperadmin.firstWhere((p) => p.id == parcialId);
  for (final paquete in parcial.paquetes) {
    for (final caso in paquete.casos) {
      if (caso.codigo == codigo) return UbicacionCaso(parcial, paquete, caso);
    }
  }
  return null;
}
