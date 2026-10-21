import { DecimalPipe } from '@angular/common';
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

const REPORTES_LINKS = [
  { label: 'Ventas', desc: 'Total vendido, metodos de pago, top productos y sucursales', route: 'ventas' },
  { label: 'Asistencia de empleados', desc: 'Horas conectadas por empleado y sucursal, segun login/logout', route: 'asistencia' },
  { label: 'Inventario', desc: 'Stock actual, alertas de stock bajo y movimientos', route: 'inventario' },
  { label: 'Reservas', desc: 'Reservas por estado y tasa de conversion a venta', route: 'reservas' },
  { label: 'Productos mas vendidos', desc: 'Ranking completo por unidades, con los que menos rotan tambien', route: 'productos' },
];

// CU16 "Gestion Reportes y Dashboards": landing con KPIs y graficos de los
// ultimos 30 dias, mas accesos a los 4 reportes detallados y filtrables.
@Component({
  selector: 'app-admin-reportes-dashboard',
  imports: [DecimalPipe, RouterLink, AppChart],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class AdminReportesDashboard implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly datos = signal<Dashboard | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly reportesLinks = REPORTES_LINKS;

  ngOnInit(): void {
    void this.cargar();
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
