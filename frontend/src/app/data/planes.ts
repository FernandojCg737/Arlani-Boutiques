// Planes de suscripción de Arlani Boutiques. Los usan la sección de Precios
// de la portada y el alta de boutiques (/empezar).
//
// Básico y Profesional siguen los requerimientos del proyecto:
//
// | Característica             | Básico   | Profesional |
// |----------------------------|----------|-------------|
// | Sucursales activas         | Hasta 2  | Hasta 10    |
// | Gestión de productos       | Sí       | Sí          |
// | Gestión de ventas          | Sí       | Sí          |
// | Reservas                   | Sí       | Sí          |
// | Operación offline          | Sí       | Sí          |
// | Reportes convencionales    | Sí       | Sí          |
// | Reportes generativos con IA| No       | Sí          |
//
// Prueba: plan gratuito por tiempo limitado para conocer la plataforma (los
// requerimientos no lo detallan; días y límites son una propuesta).
// Los montos en Bs también son una propuesta: se cambian acá y se
// actualizan en las dos pantallas.

export type Periodo = 'mensual' | 'anual';

export interface Plan {
  id: string;
  nombre: string;
  resumen: string;
  precioMensual: number;
  // Hasta cuántas sucursales activas cubre el plan.
  maxSucursales: number;
  // Plan gratuito por tiempo limitado (sin facturación mensual/anual).
  diasPrueba?: number;
  incluye: string[];
  noIncluye: string[];
}

// Pagando el año se cobran 10 meses (2 de regalo).
export const MESES_COBRADOS_AL_ANIO = 10;

const FUNCIONES_BASE = [
  'Gestión de productos',
  'Gestión de ventas',
  'Reservas',
  'Operación offline (vende sin internet)',
  'Reportes convencionales',
];

export const PLANES: Plan[] = [
  {
    id: 'prueba',
    nombre: 'Prueba',
    resumen: 'Conocé Arlani gratis antes de elegir un plan.',
    precioMensual: 0,
    maxSucursales: 1,
    diasPrueba: 14,
    incluye: ['1 sucursal activa', ...FUNCIONES_BASE],
    noIncluye: ['Reportes generativos con IA'],
  },
  {
    id: 'basico',
    nombre: 'Básico',
    resumen: 'Para la boutique que vende en línea y en mostrador.',
    precioMensual: 199,
    maxSucursales: 2,
    incluye: ['Hasta 2 sucursales activas', ...FUNCIONES_BASE],
    noIncluye: ['Reportes generativos con IA'],
  },
  {
    id: 'profesional',
    nombre: 'Profesional',
    resumen: 'Para cadenas con varias sucursales que quieren crecer con IA.',
    precioMensual: 499,
    maxSucursales: 10,
    incluye: ['Hasta 10 sucursales activas', ...FUNCIONES_BASE, 'Reportes generativos con IA'],
    noIncluye: [],
  },
];

export function esPrueba(plan: Plan): boolean {
  return plan.diasPrueba !== undefined;
}

export function precioPorMes(plan: Plan, periodo: Periodo): number {
  if (esPrueba(plan) || periodo === 'mensual') return plan.precioMensual;
  return Math.round((plan.precioMensual * MESES_COBRADOS_AL_ANIO) / 12);
}

export function precioAnual(plan: Plan): number {
  return plan.precioMensual * MESES_COBRADOS_AL_ANIO;
}

// Máximo de sucursales que admite la plataforma (plan Profesional).
export const MAX_SUCURSALES = Math.max(...PLANES.map((p) => p.maxSucursales));

// El plan pago más chico que alcanza para esa cantidad de sucursales (la
// prueba no se recomienda: es temporal).
export function planParaSucursales(cantidad: number): Plan {
  const pagos = PLANES.filter((p) => !esPrueba(p));
  return pagos.find((p) => cantidad <= p.maxSucursales) ?? pagos[pagos.length - 1];
}
