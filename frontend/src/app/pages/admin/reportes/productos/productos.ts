import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MarcaTienda } from '../../../../services/marca-tienda';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ExportarReporte } from '../../../../components/reporte/exportar-reporte';
import { environment } from '../../../../../environments/environment';

interface ProductoFila {
  producto_id: number;
  producto_nombre: string;
  categoria: string;
  marca: string;
  cantidad_vendida: number;
  total_vendido: string;
  precio_promedio: string;
  porcentaje_unidades: number;
}

interface ReporteProductos {
  resumen: { productos_distintos: number; total_unidades: number; total_vendido: string };
  detalle: ProductoFila[];
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

// CU16: ranking completo de productos vendidos (no solo el top 5 que se ve
// en el dashboard) -- deja ver tambien los que menos rotan, util para
// decidir que liquidar o sacar de catalogo.
@Component({
  selector: 'app-reporte-productos',
  imports: [DatePipe, DecimalPipe, RouterLink, ExportarReporte],
  templateUrl: './productos.html',
  styleUrl: './productos.scss',
})
export class ReporteProductosPage implements OnInit {
  // Exportar (PDF, Excel, CSV, HTML) o enviar por correo, con los filtros de la pantalla.
  protected readonly urlExportar = `${environment.apiUrl}/reportes/productos/exportar`;
  // Logo y nombre de la tienda en el encabezado del reporte.
  protected readonly marca = inject(MarcaTienda);
  private readonly http = inject(HttpClient);

  protected readonly fechaDesde = signal(primerDiaMes());
  protected readonly fechaHasta = signal(hoy());
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly tipo = signal('');
  protected readonly orden = signal<'mas' | 'menos'>('mas');
  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly datos = signal<ReporteProductos | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal('');

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

  protected params(): Record<string, string> {
    const params: Record<string, string> = {
      fecha_desde: this.fechaDesde(),
      fecha_hasta: this.fechaHasta(),
      orden: this.orden(),
    };
    if (this.sucursalId()) params['sucursal_id'] = String(this.sucursalId());
    if (this.tipo()) params['tipo'] = this.tipo();
    return params;
  }

  protected async buscar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(
        this.http.get<ReporteProductos>(`${environment.apiUrl}/reportes/productos`, { params: this.params() }),
      );
      this.datos.set(res);
    } catch {
      this.error.set('No se pudo cargar el reporte.');
    } finally {
      this.loading.set(false);
    }
  }

}
