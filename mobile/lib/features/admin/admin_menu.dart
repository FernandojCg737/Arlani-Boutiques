/// Espejo exacto de `pages/admin/admin-menu.ts` en la web: 5 paquetes con
/// sus CUs. Los que aun no tienen pantalla en la app (sin `route`) se ven
/// como "Proximamente", igual que en la web.
class AdminUseCase {
  const AdminUseCase({required this.code, required this.label, this.route, this.permiso});

  final String code;
  final String label;
  final String? route;
  // Permiso que exige (si no es el mismo codigo del CU), como en la web.
  final String? permiso;
}

class AdminPackage {
  const AdminPackage({required this.code, required this.label, required this.useCases});

  final String code;
  final String label;
  final List<AdminUseCase> useCases;
}

const adminMenu = <AdminPackage>[
  AdminPackage(
    code: 'P1',
    label: 'Gestion de Accesos y Seguridad',
    useCases: [
      AdminUseCase(code: 'CU01', label: 'Gestionar Inicio y Cierre de Sesion', route: '/admin/sesiones'),
      AdminUseCase(code: 'CU02', label: 'Administrar Usuarios, Roles y Permisos', route: '/admin/usuarios'),
      AdminUseCase(code: 'CU17', label: 'Auditar Operaciones (Bitacora)', route: '/admin/bitacora'),
      AdminUseCase(code: 'CU26', label: 'Backups y Restauracion', permiso: '2P-CU21'),
    ],
  ),
  AdminPackage(
    code: 'P2',
    label: 'Gestion de Clientes y Sucursales',
    useCases: [
      AdminUseCase(code: 'CU03', label: 'Registrar y Administrar Clientes', route: '/admin/clientes'),
      AdminUseCase(code: 'CU04', label: 'Administrar Ciudades y Sucursales', route: '/admin/sucursales'),
      AdminUseCase(code: 'CU15', label: 'Actualizar Perfil de Usuario', route: '/perfil'),
    ],
  ),
  AdminPackage(
    code: 'P3',
    label: 'Gestion de Catalogo e Inventario',
    useCases: [
      AdminUseCase(code: 'CU05', label: 'Administrar Catalogo de Productos', route: '/admin/productos'),
      AdminUseCase(code: 'CU06', label: 'Administrar Proveedores', route: '/admin/proveedores'),
      AdminUseCase(code: 'CU07', label: 'Configurar Temporadas y Colecciones', route: '/admin/temporadas'),
      AdminUseCase(code: 'CU08', label: 'Consultar Catalogo y Disponibilidad', route: '/admin/catalogo'),
      AdminUseCase(code: 'CU12', label: 'Controlar Inventario por Sucursal', route: '/admin/inventario'),
    ],
  ),
  AdminPackage(
    code: 'P4',
    label: 'Gestion de Reservas y Ventas',
    useCases: [
      AdminUseCase(code: 'CU09', label: 'Visualizar Prenda con Realidad Aumentada'),
      AdminUseCase(code: 'CU10', label: 'Gestion de Reservas', route: '/admin/reservas'),
      AdminUseCase(code: 'CU11', label: 'Gestion de Ventas', route: '/admin/ventas'),
      AdminUseCase(code: 'CU13', label: 'Administrar Carrito de Compras', route: '/admin/carritos'),
      AdminUseCase(code: 'CU21', label: 'Gestionar Metodos de Pago'),
      AdminUseCase(code: 'CU22', label: 'Arqueo y Cierre de Caja', permiso: '2P-CU16'),
      AdminUseCase(code: 'CU23', label: 'Trabajar sin Conexion', route: '/admin/sin-conexion', permiso: '2P-CU12'),
      AdminUseCase(code: 'CU24', label: 'Operaciones Offline y Conflictos', permiso: '2P-CU13'),
      AdminUseCase(code: 'CU27', label: 'Live Commerce', route: '/admin/live', permiso: '2P-CU22'),
    ],
  ),
  AdminPackage(
    code: 'P5',
    label: 'Gestion de Experiencia y Analitica',
    useCases: [
      AdminUseCase(code: 'CU14', label: 'Enviar Notificaciones', route: '/admin/notificaciones'),
      AdminUseCase(code: 'CU16', label: 'Gestion Reportes y Dashboards'),
      AdminUseCase(code: 'CU18', label: 'Recomendar Prendas por IA', route: '/admin/recomendaciones'),
      AdminUseCase(code: 'CU19', label: 'Atender Cliente con Chatbot', route: '/admin/chatbot'),
      AdminUseCase(code: 'CU20', label: 'Reputacion y Calificaciones', route: '/admin/calificaciones'),
      AdminUseCase(code: 'CU25', label: 'Reportes por Voz (IA)', permiso: '2P-CU17'),
    ],
  ),
];
