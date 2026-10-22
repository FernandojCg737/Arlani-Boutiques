import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, Signal, computed, inject } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { firstValueFrom, of } from 'rxjs';
import { catchError, debounceTime, distinctUntilChanged, map, switchMap } from 'rxjs/operators';
import { environment } from '../../environments/environment';

// Pydantic manda los Decimal como texto ("415.83"): se convierten a number
// al recibirlos para poder sumar y graficar.
const num = (v: string | number | null | undefined): number => (v == null ? 0 : Number(v));

export type PeriodoSuscripcion = 'mensual' | 'anual' | 'prueba';
export type EstadoEmpresa = 'activa' | 'suspendida';

export interface ResumenPlataforma {
  empresasTotal: number;
  empresasActivas: number;
  empresasSuspendidas: number;
  empresasPrueba: number;
  mrr: number;
  sucursalesActivas: number;
  personal: number;
  clientes: number;
  ventasMes: number;
}

export interface IngresoMes {
  mes: Date;
  ingresos: number;
}

export interface DistribucionPlan {
  codigo: string;
  nombre: string;
  empresas: number;
}

export interface EmpresaTenant {
  id: number;
  nombre: string;
  subdominio: string;
  ciudad: string | null;
  colorMarca: string;
  emailContacto: string | null;
  estado: EstadoEmpresa;
  fechaCreacion: Date;
  planCodigo: string | null;
  planNombre: string | null;
  periodo: PeriodoSuscripcion | null;
  monto: number;
  fechaFin: Date | null;
  sucursalesActivas: number;
  maxSucursales: number | null;
  usuarios: number;
  ventasTotal: number;
}

export interface PlanPlataforma {
  id: number;
  codigo: string;
  nombre: string;
  precioMensual: number;
  maxSucursales: number;
  diasPrueba: number | null;
  iaGenerativa: boolean;
  operacionOffline: boolean;
  empresas: number;
}

export interface ActividadPlataforma {
  id: number;
  accion: string;
  entidad: string;
  entidadId: number | null;
  detalle: string | null;
  fecha: Date;
  usuario: string;
}

export interface EmpresaForm {
  nombre: string;
  subdominio: string;
  ciudad: string | null;
  color_marca: string;
  email_contacto: string | null;
  plan_codigo: string;
  periodo: PeriodoSuscripcion;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function aEmpresa(e: any): EmpresaTenant {
  return {
    id: e.id,
    nombre: e.nombre,
    subdominio: e.subdominio,
    ciudad: e.ciudad,
    colorMarca: e.color_marca,
    emailContacto: e.email_contacto,
    estado: e.estado,
    fechaCreacion: new Date(e.fecha_creacion),
    planCodigo: e.plan_codigo,
    planNombre: e.plan_nombre,
    periodo: e.periodo,
    monto: num(e.monto),
    fechaFin: e.fecha_fin ? new Date(e.fecha_fin + 'T00:00:00') : null,
    sucursalesActivas: e.sucursales_activas,
    maxSucursales: e.max_sucursales,
    usuarios: e.usuarios,
    ventasTotal: num(e.ventas_total),
  };
}

function aPlan(p: any): PlanPlataforma {
  return {
    id: p.id,
    codigo: p.codigo,
    nombre: p.nombre,
    precioMensual: num(p.precio_mensual),
    maxSucursales: p.max_sucursales,
    diasPrueba: p.dias_prueba,
    iaGenerativa: p.ia_generativa,
    operacionOffline: p.operacion_offline,
    empresas: p.empresas,
  };
}

// Mensaje del backend (los PA traducidos en app/core/errores_db.py).
export function mensajeError(err: unknown, porDefecto = 'No se pudo completar la acción.'): string {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return 'Revisa los datos: ' + detail[0].msg;
    if (err.status === 0) return 'No pudimos conectar con el servidor.';
  }
  return porDefecto;
}

// Enlace de cada tienda: va por ruta (/tienda-<subdominio>) y no por
// subdominio, asi funciona en Render sin comprar un dominio propio.
export function rutaTienda(subdominio: string): string {
  return `/tienda-${subdominio}`;
}

// Enlace completo para mostrar o compartir. Toma el dominio donde corre la
// app: localhost en desarrollo y el de Render ya desplegado.
export function enlaceTienda(subdominio: string): string {
  return `${window.location.origin}${rutaTienda(subdominio)}`;
}

// Igual, sin "https://" (para mostrar en tarjetas y formularios).
export function enlaceTiendaCorto(subdominio = ''): string {
  return `${window.location.host}${rutaTienda(subdominio)}`;
}

// Enlace que quedara para una tienda nueva mientras se escribe: si ya lo usa
// otra, el backend le agrega un numero (atelier-aranier-2). Devuelve el enlace
// final para lo que se escribio, o el mismo texto mientras no hay respuesta.
// Se llama al crear el componente (contexto de inyeccion).
export function enlaceDisponible(texto: () => string): Signal<string> {
  const http = inject(HttpClient);
  const pedido = computed(texto);
  const respuesta = toSignal(
    toObservable(pedido).pipe(
      debounceTime(300),
      distinctUntilChanged(),
      switchMap((t) =>
        t.length < 3
          ? of(null)
          : http
              .get<{ subdominio: string }>(`${environment.apiUrl}/empresas/enlace-disponible`, { params: { texto: t } })
              .pipe(
                map((r) => ({ pedido: t, libre: r.subdominio })),
                catchError(() => of(null)),
              ),
      ),
    ),
    { initialValue: null },
  );
  return computed(() => {
    const r = respuesta();
    return r && r.pedido === pedido() ? r.libre : pedido();
  });
}

// Panel del SuperAdministrador: CU09 (empresas) y CU10 (planes y límites).
@Injectable({ providedIn: 'root' })
export class PlataformaApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/plataforma`;

  async resumen(): Promise<ResumenPlataforma> {
    const r: any = await firstValueFrom(this.http.get(`${this.base}/resumen`));
    return {
      empresasTotal: r.empresas_total,
      empresasActivas: r.empresas_activas,
      empresasSuspendidas: r.empresas_suspendidas,
      empresasPrueba: r.empresas_prueba,
      mrr: num(r.mrr),
      sucursalesActivas: r.sucursales_activas,
      personal: r.personal,
      clientes: r.clientes,
      ventasMes: num(r.ventas_mes),
    };
  }

  async ingresos(meses = 6): Promise<IngresoMes[]> {
    const r: any[] = await firstValueFrom(this.http.get<any[]>(`${this.base}/ingresos`, { params: { meses } }));
    return r.map((i) => ({ mes: new Date(i.mes + 'T00:00:00'), ingresos: num(i.ingresos) }));
  }

  async distribucionPlanes(): Promise<DistribucionPlan[]> {
    return firstValueFrom(this.http.get<DistribucionPlan[]>(`${this.base}/distribucion-planes`));
  }

  async actividad(limite = 12): Promise<ActividadPlataforma[]> {
    const r: any[] = await firstValueFrom(this.http.get<any[]>(`${this.base}/actividad`, { params: { limite } }));
    return r.map((a) => ({
      id: a.id,
      accion: a.accion,
      entidad: a.entidad_afectada,
      entidadId: a.entidad_id,
      detalle: a.detalle,
      fecha: new Date(a.fecha + 'Z'),
      usuario: a.usuario_nombre,
    }));
  }

  async empresas(): Promise<EmpresaTenant[]> {
    const r: any[] = await firstValueFrom(this.http.get<any[]>(`${this.base}/empresas`));
    return r.map(aEmpresa);
  }

  async crearEmpresa(datos: EmpresaForm): Promise<EmpresaTenant> {
    return aEmpresa(await firstValueFrom(this.http.post(`${this.base}/empresas`, datos)));
  }

  async actualizarEmpresa(
    id: number,
    datos: Pick<EmpresaForm, 'nombre' | 'ciudad' | 'color_marca' | 'email_contacto'>,
  ): Promise<EmpresaTenant> {
    return aEmpresa(await firstValueFrom(this.http.put(`${this.base}/empresas/${id}`, datos)));
  }

  async cambiarEstado(id: number, estado: EstadoEmpresa): Promise<EmpresaTenant> {
    return aEmpresa(await firstValueFrom(this.http.patch(`${this.base}/empresas/${id}/estado`, { estado })));
  }

  async cambiarPlan(id: number, planCodigo: string, periodo: PeriodoSuscripcion): Promise<EmpresaTenant> {
    return aEmpresa(
      await firstValueFrom(this.http.patch(`${this.base}/empresas/${id}/plan`, { plan_codigo: planCodigo, periodo })),
    );
  }

  async eliminarEmpresa(id: number): Promise<void> {
    await firstValueFrom(this.http.delete(`${this.base}/empresas/${id}`));
  }

  async planes(): Promise<PlanPlataforma[]> {
    const r: any[] = await firstValueFrom(this.http.get<any[]>(`${this.base}/planes`));
    return r.map(aPlan);
  }

  async actualizarPlan(
    codigo: string,
    datos: { precio_mensual: number; max_sucursales: number; ia_generativa: boolean },
  ): Promise<PlanPlataforma> {
    return aPlan(await firstValueFrom(this.http.put(`${this.base}/planes/${codigo}`, datos)));
  }
}
