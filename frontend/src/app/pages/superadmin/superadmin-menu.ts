// Menú del SuperAdministrador: dos parciales, cada uno con sus paquetes y
// casos de uso. Las rutas son relativas a /superadmin.
//
// Los CUs del 1er parcial que se mejoran en el 2do ya no están en el 1ro:
// quedan en el 2do con su número nuevo (ver `antes`) y en el 1ro solo se
// deja la referencia en `movidos`.

export type ParcialId = 'p1' | 'p2';

export interface SubAcceso {
  etiqueta: string;
  ruta: string;
}

export interface CasoUsoMenu {
  codigo: string;
  nombre: string;
  // Pantalla donde opera; sin ruta = en construcción (/superadmin/cu/<codigo>).
  ruta?: string;
  // Número que tenía en el 1er parcial.
  antes?: string;
  subs?: SubAcceso[];
  // Se elige primero la empresa (tienda) y la pantalla muestra solo lo suyo.
  // Falso para lo personal (perfil) y lo de toda la plataforma.
  porEmpresa?: boolean;
  plataformas?: ('WEB' | 'MÓVIL')[];
  descripcion?: string;
  // Permisos (tabla permiso) que habilita este CU en la matriz de CU02. Los
  // CUs mejorados reusan el permiso del 1er parcial; los nuevos usan "2P-".
  // Si no se indica, es el mismo código del CU.
  permisos?: string[];
}

export interface MovidoMenu {
  de: string;
  a: string;
  nombre: string;
}

export interface PaqueteMenu {
  codigo: string;
  nombre: string;
  casos: CasoUsoMenu[];
  movidos?: MovidoMenu[];
}

export interface ParcialMenu {
  id: ParcialId;
  nombre: string;
  paquetes: PaqueteMenu[];
}

export const PARCIALES: ParcialMenu[] = [
  {
    id: 'p1',
    nombre: '1er Parcial',
    paquetes: [
      {
        codigo: 'P1',
        nombre: 'Gestión de Accesos y Seguridad',
        casos: [],
        movidos: [
          { de: 'CU01', a: 'CU01', nombre: 'Gestionar inicio y cierre de sesión' },
          { de: 'CU02', a: 'CU02', nombre: 'Administrar usuarios, roles y permisos' },
          { de: 'CU17', a: 'CU08', nombre: 'Auditar operaciones (bitácora)' },
        ],
      },
      {
        codigo: 'P2',
        nombre: 'Gestión de Clientes y Sucursales',
        casos: [
          { codigo: 'CU03', nombre: 'Registrar y Administrar Clientes', ruta: 'clientes', porEmpresa: true },
          { codigo: 'CU15', nombre: 'Actualizar Perfil de Usuario', ruta: 'perfil' },
        ],
        movidos: [{ de: 'CU04', a: 'CU03', nombre: 'Administrar ciudades y sucursales' }],
      },
      {
        codigo: 'P3',
        nombre: 'Gestión de Catálogo e Inventario',
        casos: [
          { codigo: 'CU06', nombre: 'Administrar Proveedores', ruta: 'proveedores', porEmpresa: true },
          { codigo: 'CU07', nombre: 'Configurar Temporadas y Colecciones', ruta: 'temporadas', porEmpresa: true },
        ],
        movidos: [
          { de: 'CU05', a: 'CU04', nombre: 'Administrar catálogo de productos' },
          { de: 'CU08', a: 'CU04', nombre: 'Consultar catálogo y disponibilidad' },
          { de: 'CU12', a: 'CU04', nombre: 'Controlar inventario por sucursal' },
        ],
      },
      {
        codigo: 'P4',
        nombre: 'Gestión de Reservas y Ventas',
        casos: [
          { codigo: 'CU09', nombre: 'Visualizar Prenda con Realidad Aumentada', ruta: 'ar-uso', porEmpresa: true },
          { codigo: 'CU13', nombre: 'Administrar Carrito de Compras', ruta: 'carritos', porEmpresa: true },
        ],
        movidos: [
          { de: 'CU10', a: 'CU05', nombre: 'Gestión de reservas' },
          { de: 'CU11', a: 'CU06', nombre: 'Gestión de ventas' },
        ],
      },
      {
        codigo: 'P5',
        nombre: 'Gestión de Experiencia y Analítica',
        casos: [
          { codigo: 'CU14', nombre: 'Enviar Notificaciones', ruta: 'notificaciones', porEmpresa: true },
          { codigo: 'CU19', nombre: 'Atender Cliente con Chatbot', ruta: 'chatbot', porEmpresa: true },
          { codigo: 'CU20', nombre: 'Reputación y Calificaciones', ruta: 'calificaciones', porEmpresa: true },
        ],
        movidos: [
          { de: 'CU16', a: 'CU07', nombre: 'Gestión de reportes y dashboards' },
          { de: 'CU18', a: 'CU18', nombre: 'Recomendar prendas por IA' },
        ],
      },
    ],
  },
  {
    id: 'p2',
    nombre: '2do Parcial',
    paquetes: [
      {
        codigo: 'P1',
        nombre: 'Seguridad y Acceso',
        casos: [
          { codigo: 'CU01', nombre: 'Gestionar inicio y cierre de sesión', ruta: 'sesiones', antes: 'CU01', plataformas: ['WEB', 'MÓVIL'] },
          { codigo: 'CU02', nombre: 'Administrar usuarios, roles y permisos', ruta: 'usuarios', antes: 'CU02', plataformas: ['WEB', 'MÓVIL'] },
          { codigo: 'CU08', permisos: ['CU17'], nombre: 'Auditar operaciones (bitácora)', ruta: 'bitacora', antes: 'CU17', plataformas: ['WEB'] },
        ],
      },
      {
        codigo: 'P2',
        nombre: 'Plataforma SaaS',
        casos: [
          { codigo: 'CU09', permisos: ['2P-CU09'], nombre: 'Gestionar empresas (tenants)', ruta: 'empresas', plataformas: ['WEB'] },
          {
            codigo: 'CU10', permisos: ['2P-CU10'],
            nombre: 'Gestionar y verificar planes, suscripciones y límites',
            ruta: 'planes',
            plataformas: ['WEB', 'MÓVIL'],
            subs: [
              { etiqueta: 'Planes y suscripciones', ruta: 'planes' },
              { etiqueta: 'Comisiones por tienda', ruta: 'comisiones' },
            ],
          },
        ],
      },
      {
        codigo: 'P3',
        nombre: 'Operación de Tiendas',
        casos: [
          { codigo: 'CU03', permisos: ['CU04'], nombre: 'Administrar ciudades y sucursales', ruta: 'sucursales', antes: 'CU04', plataformas: ['WEB'], porEmpresa: true },
          {
            codigo: 'CU04', permisos: ['CU05', 'CU08', 'CU12'],
            nombre: 'Catálogo e inventario',
            ruta: 'productos',
            antes: 'CU05 · CU08 · CU12',
            plataformas: ['WEB'],
            porEmpresa: true,
            subs: [
              { etiqueta: 'Productos', ruta: 'productos' },
              { etiqueta: 'Catálogo y disponibilidad', ruta: 'catalogo' },
              { etiqueta: 'Inventario por sucursal', ruta: 'inventario' },
            ],
          },
          { codigo: 'CU05', permisos: ['CU10'], nombre: 'Gestionar reservas (online y offline)', ruta: 'reservas', antes: 'CU10', plataformas: ['WEB', 'MÓVIL'], porEmpresa: true },
          { codigo: 'CU06', permisos: ['CU11'], nombre: 'Gestionar ventas (online y offline)', ruta: 'ventas', antes: 'CU11', plataformas: ['WEB', 'MÓVIL'], porEmpresa: true },
          {
            codigo: 'CU19', permisos: ['CU21'],
            nombre: 'Gestionar métodos de pago',
            ruta: 'metodos-pago',
            plataformas: ['WEB'],
            porEmpresa: true,
            descripcion:
              'Cada tienda registra cómo le pagan: su PayPal (con sus credenciales), QR, transferencia u otros. Los pagos con comprobante los aprueba el personal.',
          },
          {
            codigo: 'CU15', permisos: ['2P-CU15'],
            nombre: 'Gestionar cambio de prendas',
            ruta: 'cambios',
            plataformas: ['WEB', 'MÓVIL'],
            porEmpresa: true,
            descripcion:
              'Cambiar una prenda vendida por otra (talla, color o modelo), ajustando el stock de la sucursal y la diferencia de precio. Parte de la base de devoluciones del 1er parcial.',
          },
          {
            codigo: 'CU16', permisos: ['2P-CU16'],
            nombre: 'Arqueo y cierre de caja',
            ruta: 'caja',
            plataformas: ['WEB', 'MÓVIL'],
            porEmpresa: true,
            descripcion:
              'Caja física por sucursal (se abre con fondo inicial y se cierra contando el efectivo) y caja online diaria automática; historial de cajas con todas sus ventas.',
          },
        ],
      },
      {
        codigo: 'P4',
        nombre: 'Offline y Sincronización',
        casos: [
          {
            codigo: 'CU11', permisos: ['2P-CU11'],
            nombre: 'Descargar y consultar catálogo offline',
            ruta: 'descargas-offline',
            plataformas: ['WEB', 'MÓVIL'],
            porEmpresa: true,
            descripcion: 'Guardar el catálogo en el dispositivo (SQLite en la app, PWA en la web) para consultarlo sin conexión.',
          },
          {
            codigo: 'CU12', permisos: ['2P-CU12'],
            nombre: 'Sincronizar operaciones pendientes',
            ruta: 'sincronizacion-offline',
            plataformas: ['WEB', 'MÓVIL'],
            porEmpresa: true,
            descripcion: 'Enviar al servidor las ventas y reservas hechas sin internet apenas vuelve la conexión.',
          },
          {
            codigo: 'CU13', permisos: ['2P-CU13'],
            nombre: 'Consultar operaciones locales y su estado',
            ruta: 'operaciones-offline',
            plataformas: ['WEB', 'MÓVIL'],
            porEmpresa: true,
            descripcion: 'Ver cada operación guardada en el dispositivo: pendiente, sincronizada o en conflicto.',
          },
          {
            codigo: 'CU14', permisos: ['2P-CU14'],
            nombre: 'Gestionar conflictos de sincronización',
            ruta: 'conflictos',
            plataformas: ['WEB'],
            porEmpresa: true,
            descripcion: 'Resolver operaciones que chocan al sincronizar (por ejemplo, stock vendido dos veces).',
          },
        ],
      },
      {
        codigo: 'P5',
        nombre: 'Inteligencia y Reportes',
        casos: [
          {
            codigo: 'CU07', permisos: ['CU16'],
            nombre: 'Gestionar reportes y dashboards',
            ruta: 'reportes',
            antes: 'CU16',
            plataformas: ['WEB'],
            porEmpresa: true,
            subs: [
              { etiqueta: 'Dashboard', ruta: 'reportes' },
              { etiqueta: 'Ventas', ruta: 'reportes/ventas' },
              { etiqueta: 'Asistencia', ruta: 'reportes/asistencia' },
              { etiqueta: 'Inventario', ruta: 'reportes/inventario' },
              { etiqueta: 'Reservas', ruta: 'reportes/reservas' },
              { etiqueta: 'Productos', ruta: 'reportes/productos' },
              { etiqueta: 'Dinámico', ruta: 'reportes/dinamico' },
            ],
          },
          {
            codigo: 'CU17', permisos: ['2P-CU17'],
            nombre: 'Solicitar y exportar reporte generativo (texto o voz)',
            plataformas: ['WEB', 'MÓVIL'],
            descripcion:
              'Pedir un reporte en lenguaje natural, por texto o por voz, y exportarlo. Disponible solo en el plan Profesional.',
          },
          { codigo: 'CU18', nombre: 'Gestionar modelos de ML', ruta: 'recomendaciones', antes: 'CU18', plataformas: ['WEB'] },
          {
            codigo: 'CU20',
            nombre: 'Gestionar reportes de la plataforma (SaaS)',
            ruta: 'reportes-saas',
            plataformas: ['WEB'],
            descripcion:
              'Lo que gana Arlani: suscripciones y comisiones por ventas, MRR, tiendas, planes y vencimientos. Reportes fijos y dinámicos; PDF, Excel, CSV, HTML y envío por correo.',
          },
        ],
      },
    ],
  },
];

export interface UbicacionCu {
  parcial: ParcialMenu;
  paquete: PaqueteMenu;
  caso: CasoUsoMenu;
}

// Busca un CU por su código dentro de un parcial.
export function buscarCaso(parcial: ParcialId, codigo: string): UbicacionCu | null {
  const p = PARCIALES.find((x) => x.id === parcial);
  for (const paquete of p?.paquetes ?? []) {
    const caso = paquete.casos.find((c) => c.codigo === codigo);
    if (caso && p) return { parcial: p, paquete, caso };
  }
  return null;
}

// Dónde está la pantalla de una ruta (primera coincidencia; el 2do parcial
// tiene prioridad porque ahí viven los CUs mejorados).
export function ubicarRuta(ruta: string): UbicacionCu | null {
  for (const id of ['p2', 'p1'] as ParcialId[]) {
    const p = PARCIALES.find((x) => x.id === id)!;
    for (const paquete of p.paquetes) {
      for (const caso of paquete.casos) {
        const rutas = [caso.ruta, ...(caso.subs ?? []).map((s) => s.ruta)];
        if (rutas.includes(ruta)) return { parcial: p, paquete, caso };
      }
    }
  }
  return null;
}

// Permisos que controla un CU (por defecto, su propio código).
export function permisosDe(caso: CasoUsoMenu): string[] {
  return caso.permisos ?? [caso.codigo];
}
