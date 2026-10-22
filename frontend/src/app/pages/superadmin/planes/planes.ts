import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { EmpresaTenant, PlanPlataforma, PlataformaApi, mensajeError } from '../../../services/plataforma';
import { AvisosPanel } from '../avisos';

interface Borrador {
  precio: number;
  max: number;
  ia: boolean;
}

// Funciones que todos los planes incluyen (requerimiento del proyecto). La
// operación offline y la IA dependen del plan (columnas de plan_suscripcion).
const FUNCIONES_BASE = ['Gestión de productos', 'Gestión de ventas', 'Reservas', 'Reportes convencionales'];

// CU10 Gestionar y verificar planes, suscripciones y límites.
@Component({
  selector: 'app-superadmin-planes',
  imports: [DecimalPipe],
  templateUrl: './planes.html',
  styleUrl: './planes.scss',
})
export class SuperadminPlanes implements OnInit {
  private readonly api = inject(PlataformaApi);
  private readonly avisos = inject(AvisosPanel);

  protected readonly funcionesBase = FUNCIONES_BASE;
  protected readonly cargando = signal(true);
  protected readonly planes = signal<PlanPlataforma[]>([]);
  protected readonly empresas = signal<EmpresaTenant[]>([]);
  protected readonly borradores = signal<Record<string, Borrador>>({});
  protected readonly guardando = signal<string | null>(null);

  protected readonly empresasConPlan = computed(() =>
    this.empresas()
      .filter((e) => e.maxSucursales)
      .map((e) => ({ ...e, pct: Math.min(100, Math.round((e.sucursalesActivas / e.maxSucursales!) * 100)) }))
      .sort((a, b) => b.pct - a.pct),
  );

  async ngOnInit(): Promise<void> {
    try {
      const [planes, empresas] = await Promise.all([this.api.planes(), this.api.empresas()]);
      this.planes.set(planes);
      this.empresas.set(empresas);
      this.reiniciarBorradores(planes);
    } catch (err) {
      this.avisos.error(mensajeError(err, 'No pudimos cargar los planes.'));
    } finally {
      this.cargando.set(false);
    }
  }

  private reiniciarBorradores(planes: PlanPlataforma[]): void {
    const b: Record<string, Borrador> = {};
    for (const p of planes) b[p.codigo] = { precio: p.precioMensual, max: p.maxSucursales, ia: p.iaGenerativa };
    this.borradores.set(b);
  }

  protected borrador(codigo: string): Borrador {
    return this.borradores()[codigo] ?? { precio: 0, max: 1, ia: false };
  }

  protected editar(codigo: string, cambio: Partial<Borrador>): void {
    this.borradores.update((b) => ({ ...b, [codigo]: { ...b[codigo], ...cambio } }));
  }

  protected sumarSucursales(codigo: string, delta: number): void {
    const actual = this.borrador(codigo).max;
    this.editar(codigo, { max: Math.max(1, Math.min(500, actual + delta)) });
  }

  protected cambiado(p: PlanPlataforma): boolean {
    const b = this.borrador(p.codigo);
    return b.precio !== p.precioMensual || b.max !== p.maxSucursales || b.ia !== p.iaGenerativa;
  }

  protected descartar(p: PlanPlataforma): void {
    this.editar(p.codigo, { precio: p.precioMensual, max: p.maxSucursales, ia: p.iaGenerativa });
  }

  protected async guardar(p: PlanPlataforma): Promise<void> {
    const b = this.borrador(p.codigo);
    if (!(b.precio >= 0) || !(b.max >= 1)) {
      this.avisos.error('Revisa el precio y el límite de sucursales.');
      return;
    }
    this.guardando.set(p.codigo);
    try {
      const actualizado = await this.api.actualizarPlan(p.codigo, {
        precio_mensual: b.precio,
        max_sucursales: b.max,
        ia_generativa: b.ia,
      });
      this.planes.update((l) => l.map((x) => (x.codigo === p.codigo ? actualizado : x)));
      // Los límites de las empresas dependen del plan: se refrescan.
      this.empresas.set(await this.api.empresas());
      this.avisos.exito(`Plan ${actualizado.nombre} actualizado.`);
    } catch (err) {
      this.avisos.error(mensajeError(err));
      this.descartar(p);
    } finally {
      this.guardando.set(null);
    }
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }
}
