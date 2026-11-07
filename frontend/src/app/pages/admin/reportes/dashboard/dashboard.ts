import { DecimalPipe, PercentPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../../environments/environment';
import { AppChart } from '../../../../components/chart/chart';

interface SerieDia {
  fecha: string;
  total: string;
  cantidad: number;
}

interface SerieCategoria {
  etiqueta: string;
  total: string;
  cantidad: number;
}

interface Dashboard {
  ventas_hoy_total: string;
  ventas_hoy_cantidad: number;
  ventas_mes_total: string;
  ventas_mes_cantidad: number;
  ticket_promedio_mes: string;
  reservas_activas: number;
  clientes_nuevos_mes: number;
  ventas_por_dia: SerieDia[];
  ventas_por_metodo: SerieCategoria[];
  ventas_por_sucursal: SerieCategoria[];
  top_productos: SerieCategoria[];
}

// CU18: pronostico de ventas (modelo supervisado de regresion) por sucursal.
export interface Pronostico {
  algoritmo: string;
  metricas: { mae: number; rmse: number; r2: number | null; error_pct: number | null; error_total_pct: number | null };
  semanas: string[];
  pronostico_total: number[];
  ultimas_4_semanas: number[];
  variacion: number | null;
  datos_hasta: string;
  sucursales: {
    sucursal_id: number;
    sucursal: string;
    semanas: number[];
    total_pronostico: number;
    total_ultimas_4: number;
  }[];
}

const REPORTES_LINKS = [
  { label: 'Ventas', desc: 'Total vendido, metodos de pago, top productos y sucursales', route: 'ventas' },
  { label: 'Asistencia de empleados', desc: 'Horas conectadas por empleado y sucursal, segun login/logout', route: 'asistencia' },
  { label: 'Inventario', desc: 'Stock actual, alertas de stock bajo y movimientos', route: 'inventario' },
  { label: 'Reservas', desc: 'Reservas por estado y tasa de conversion a venta', route: 'reservas' },
  { label: 'Productos mas vendidos', desc: 'Ranking completo por unidades, con los que menos rotan tambien', route: 'productos' },
  { label: 'Reporte dinamico', desc: 'Arma tu reporte: elige los datos, como agruparlos y que medir', route: 'dinamico' },
];

// CU16 "Gestion Reportes y Dashboards": landing con KPIs y graficos de los
// ultimos 30 dias, mas accesos a los 4 reportes detallados y filtrables.
@Component({
  selector: 'app-admin-reportes-dashboard',
  imports: [DecimalPipe, PercentPipe, RouterLink, AppChart],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class AdminReportesDashboard implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly datos = signal<Dashboard | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly reportesLinks = REPORTES_LINKS;

  protected readonly pronostico = signal<Pronostico | null>(null);
  protected readonly pronosticoError = signal('');

  ngOnInit(): void {
    void this.cargar();
    void this.cargarPronostico();
  }

  private async cargarPronostico(): Promise<void> {
    try {
      this.pronostico.set(await firstValueFrom(this.http.get<Pronostico>(`${environment.apiUrl}/reportes/pronostico`)));
    } catch (err: unknown) {
      const detalle = (err as { error?: { detail?: string } })?.error?.detail;
      this.pronosticoError.set(typeof detalle === 'string' ? detalle : 'No se pudo calcular el pronóstico.');
    }
  }

  // Grafico: las 4 semanas reales y las 4 pronosticadas (la linea del
  // pronostico arranca en la ultima semana real para que se vean unidas).
  protected labelsPronostico(p: Pronostico): string[] {
    return ['Hace 4 sem.', 'Hace 3 sem.', 'Hace 2 sem.', 'Última sem.', ...p.semanas];
  }

  protected seriesPronostico(p: Pronostico): { label: string; data: (number | null)[] }[] {
    const reales = p.ultimas_4_semanas;
    return [
      { label: 'Vendido (Bs)', data: [...reales, null, null, null, null] },
      { label: 'Pronóstico (Bs)', data: [null, null, null, reales[3] ?? null, ...p.pronostico_total] },
    ];
  }

  protected suma(valores: number[]): number {
    return valores.reduce((t, v) => t + v, 0);
  }

  private async cargar(): Promise<void> {
    this.loading.set(true);
    try {
      const res = await firstValueFrom(this.http.get<Dashboard>(`${environment.apiUrl}/reportes/dashboard`));
      this.datos.set(res);
    } catch {
      this.error.set('No se pudo cargar el dashboard.');
    } finally {
      this.loading.set(false);
    }
  }

  protected labelsDias(): string[] {
    return (this.datos()?.ventas_por_dia ?? []).map((d) =>
      new Date(d.fecha + 'T00:00:00').toLocaleDateString('es-BO', { day: '2-digit', month: '2-digit' }),
    );
  }

  protected dataDias(): number[] {
    return (this.datos()?.ventas_por_dia ?? []).map((d) => Number(d.total));
  }

  protected labelsMetodo(): string[] {
    return (this.datos()?.ventas_por_metodo ?? []).map((d) => d.etiqueta);
  }

  protected dataMetodo(): number[] {
    return (this.datos()?.ventas_por_metodo ?? []).map((d) => Number(d.total));
  }

  protected labelsProductos(): string[] {
    return (this.datos()?.top_productos ?? []).map((d) => d.etiqueta);
  }

  protected dataProductos(): number[] {
    return (this.datos()?.top_productos ?? []).map((d) => d.cantidad);
  }

  protected labelsSucursal(): string[] {
    return (this.datos()?.ventas_por_sucursal ?? []).map((d) => d.etiqueta);
  }

  protected dataSucursal(): number[] {
    return (this.datos()?.ventas_por_sucursal ?? []).map((d) => Number(d.total));
  }
}
