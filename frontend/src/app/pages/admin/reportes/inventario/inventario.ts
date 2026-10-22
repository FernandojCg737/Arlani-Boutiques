import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MarcaTienda } from '../../../../services/marca-tienda';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../../environments/environment';
import { descargarArchivo } from '../reportes-export';

interface StockFila {
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  sucursal_nombre: string;
  cantidad: number;
}

interface MovimientoFila {
  fecha: string;
  tipo: string;
  cantidad: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  sucursal_nombre: string;
  empleado_nombre: string | null;
  documento_referencia: string | null;
}

interface ReporteInventario {
  resumen: { productos_distintos: number; unidades_en_stock: number; alertas_stock_bajo: number };
  stock: StockFila[];
  alertas: StockFila[];
  movimientos: MovimientoFila[];
}

interface Sucursal {
  id: number;
  nombre: string;
}

function hace30Dias(): string {
  const d = new Date();
  d.setDate(d.getDate() - 29);
  return d.toISOString().slice(0, 10);
}

function hoy(): string {
  return new Date().toISOString().slice(0, 10);
}

@Component({
  selector: 'app-reporte-inventario',
  imports: [DatePipe, RouterLink],
  templateUrl: './inventario.html',
  styleUrl: './inventario.scss',
})
export class ReporteInventarioPage implements OnInit {
  // Logo y nombre de la tienda en el encabezado del reporte.
  protected readonly marca = inject(MarcaTienda);
  private readonly http = inject(HttpClient);

  protected readonly fechaDesde = signal(hace30Dias());
  protected readonly fechaHasta = signal(hoy());
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly umbral = signal(5);
  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly datos = signal<ReporteInventario | null>(null);
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
    const params: Record<string, string> = {
      fecha_desde: this.fechaDesde(),
      fecha_hasta: this.fechaHasta(),
      umbral: String(this.umbral()),
    };
    if (this.sucursalId()) params['sucursal_id'] = String(this.sucursalId());
    return params;
  }

  protected async buscar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(
        this.http.get<ReporteInventario>(`${environment.apiUrl}/reportes/inventario`, { params: this.params() }),
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
      const params: Record<string, string> = { formato, umbral: String(this.umbral()) };
      if (this.sucursalId()) params['sucursal_id'] = String(this.sucursalId());
      const blob = await firstValueFrom(
        this.http.get(`${environment.apiUrl}/reportes/inventario/exportar`, { params, responseType: 'blob' }),
      );
      descargarArchivo(blob, `reporte_inventario.${formato === 'excel' ? 'xlsx' : 'csv'}`);
    } catch {
      this.error.set('No se pudo exportar el reporte.');
    } finally {
      this.exportando.set(false);
    }
  }
}
