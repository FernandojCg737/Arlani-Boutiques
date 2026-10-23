export interface AdminUseCase {
  code: string;
  label: string;
  route?: string;
}

export interface AdminPackage {
  code: string;
  label: string;
  useCases: AdminUseCase[];
}

export const ADMIN_MENU: AdminPackage[] = [
  {
    code: 'P1',
    label: 'Gestion de Accesos y Seguridad',
    useCases: [
      { code: 'CU01', label: 'Gestionar Inicio y Cierre de Sesion', route: '/admin/sesiones' },
      { code: 'CU02', label: 'Administrar Usuarios, Roles y Permisos', route: '/admin/usuarios' },
      { code: 'CU17', label: 'Auditar Operaciones (Bitacora)', route: '/admin/bitacora' },
    ],
  },
  {
    code: 'P2',
    label: 'Gestion de Clientes y Sucursales',
    useCases: [
      { code: 'CU03', label: 'Registrar y Administrar Clientes', route: '/admin/clientes' },
      { code: 'CU04', label: 'Administrar Ciudades y Sucursales', route: '/admin/sucursales' },
      { code: 'CU15', label: 'Actualizar Perfil de Usuario', route: '/admin/perfil' },
    ],
  },
  {
    code: 'P3',
    label: 'Gestion de Catalogo e Inventario',
    useCases: [
      { code: 'CU05', label: 'Administrar Catalogo de Productos', route: '/admin/productos' },
      { code: 'CU06', label: 'Administrar Proveedores', route: '/admin/proveedores' },
      { code: 'CU07', label: 'Configurar Temporadas y Colecciones', route: '/admin/temporadas' },
      { code: 'CU08', label: 'Consultar Catalogo y Disponibilidad', route: '/admin/catalogo' },
      { code: 'CU12', label: 'Controlar Inventario por Sucursal', route: '/admin/inventario' },
    ],
  },
  {
    code: 'P4',
    label: 'Gestion de Reservas y Ventas',
    useCases: [
      { code: 'CU09', label: 'Visualizar Prenda con Realidad Aumentada', route: '/admin/ar-uso' },
      { code: 'CU10', label: 'Gestion de Reservas', route: '/admin/reservas' },
      { code: 'CU11', label: 'Gestion de Ventas', route: '/admin/ventas' },
      { code: 'CU13', label: 'Administrar Carrito de Compras', route: '/admin/carritos' },
      { code: 'CU21', label: 'Gestionar Metodos de Pago', route: '/admin/metodos-pago' },
    ],
  },
  {
    code: 'P5',
    label: 'Gestion de Experiencia y Analitica',
    useCases: [
      { code: 'CU14', label: 'Enviar Notificaciones', route: '/admin/notificaciones' },
      { code: 'CU16', label: 'Gestion Reportes y Dashboards', route: '/admin/reportes' },
      { code: 'CU18', label: 'Recomendar Prendas por IA', route: '/admin/recomendaciones' },
      { code: 'CU19', label: 'Atender Cliente con Chatbot', route: '/admin/chatbot' },
      { code: 'CU20', label: 'Reputacion y Calificaciones', route: '/admin/calificaciones' },
    ],
  },
];
