import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MarcaTienda } from '../../../../services/marca-tienda';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../../environments/environment';
import { descargarArchivo } from '../reportes-export';

interface SerieCategoria {
  etiqueta: string;
  total: string;
  cantidad: number;
}

interface VentaFila {
  id: number;
  fecha: string;
  cliente_nombre: string;
  sucursal_nombre: string;
  tipo: string;
  metodo_pago: string;
  estado_pago: string;
  total: string;
}

interface ReporteVentas {
  resumen: { total_vendido: string; cantidad_ventas: number; ticket_promedio: string };
  por_metodo: SerieCategoria[];
  por_sucursal: SerieCategoria[];
  top_productos: SerieCategoria[];
  detalle: VentaFila[];
}

interface Sucursal {
  id: number;
  nombre: string;
}

function primerDiaMes(): string {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

function hoy(): string {
  return new Date().toISOString().slice(0, 10);
}

@Component({
  selector: 'app-reporte-ventas',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './ventas.html',
  styleUrl: './ventas.scss',
})
export class ReporteVentasPage implements OnInit {
  // Logo y nombre de la tienda en el encabezado del reporte.
  protected readonly marca = inject(MarcaTienda);
  private readonly http = inject(HttpClient);

  protected readonly fechaDesde = signal(primerDiaMes());
  protected readonly fechaHasta = signal(hoy());
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly tipo = signal('');
  protected readonly metodo = signal('');
  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly datos = signal<ReporteVentas | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly exportando = signal(false);

  ngOnInit(): void {
    void this.cargarSucursales();
    void this.buscar();
  }

  private async cargarSucursales(): Promise<void> {
    try {
      const res = await firstValueFrom(this.http.get<Sucursal[]>(`${environment.apiUrl}/sucursales/publico`));
      this.sucursales.set(res);
    } catch {
      this.sucursales.set([]);
    }
  }

  private params(): Record<string, string> {
    const params: Record<string, string> = { fecha_desde: this.fechaDesde(), fecha_hasta: this.fechaHasta() };
    if (this.sucursalId()) params['sucursal_id'] = String(this.sucursalId());
    if (this.tipo()) params['tipo'] = this.tipo();
    if (this.metodo()) params['metodo'] = this.metodo();
    return params;
  }

  protected async buscar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(
        this.http.get<ReporteVentas>(`${environment.apiUrl}/reportes/ventas`, { params: this.params() }),
      );
      this.datos.set(res);
    } catch {
      this.error.set('No se pudo cargar el reporte.');
    } finally {
      this.loading.set(false);
    }
  }

  protected imprimir(): void {
    window.print();
  }

  protected async exportar(formato: 'csv' | 'excel'): Promise<void> {
    this.exportando.set(true);
    try {
      const blob = await firstValueFrom(
        this.http.get(`${environment.apiUrl}/reportes/ventas/exportar`, {
          params: { ...this.params(), formato },
          responseType: 'blob',
        }),
      );
      descargarArchivo(blob, `reporte_ventas.${formato === 'excel' ? 'xlsx' : 'csv'}`);
    } catch {
      this.error.set('No se pudo exportar el reporte.');
    } finally {
      this.exportando.set(false);
    }
  }
}
