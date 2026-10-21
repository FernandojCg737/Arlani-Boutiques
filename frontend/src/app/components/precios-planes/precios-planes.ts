import { Component, computed, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  MAX_SUCURSALES,
  PLANES,
  Periodo,
  Plan,
  esPrueba,
  planParaSucursales,
  precioAnual,
  precioPorMes,
} from '../../data/planes';

// Precios de la plataforma. Los planes están en data/planes.ts (los comparte
// con el alta de boutiques).
@Component({
  selector: 'app-precios-planes',
  imports: [RouterLink],
  templateUrl: './precios-planes.html',
  styleUrl: './precios-planes.scss',
})
export class PreciosPlanes {
  protected readonly planes = PLANES;
  protected readonly maxSucursales = MAX_SUCURSALES;
  protected readonly esPrueba = esPrueba;
  protected readonly periodo = signal<Periodo>('mensual');
  protected readonly sucursales = signal(2);

  protected readonly recomendado = computed(() => planParaSucursales(this.sucursales()).id);

  protected precioPorMes(plan: Plan): number {
    return precioPorMes(plan, this.periodo());
  }

  protected precioAnual(plan: Plan): number {
    return precioAnual(plan);
  }

  protected alMoverSucursales(evento: Event): void {
    this.sucursales.set(Number((evento.target as HTMLInputElement).value));
  }
}
