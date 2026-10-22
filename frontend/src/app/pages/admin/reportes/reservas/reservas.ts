import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MarcaTienda } from '../../../../services/marca-tienda';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../../environments/environment';
import { descargarArchivo } from '../reportes-export';

interface ReservaFila {
  id: number;
  fecha_creacion: string;
  cliente_nombre: string;
  sucursal_nombre: string;
  horario_atencion: string;
  estado: string;
}

interface ReporteReservas {
  resumen: {
    total: number;
    pendientes: number;
    confirmadas: number;
    completadas: number;
    canceladas: number;
    vencidas: number;
    tasa_conversion: number;
  };
  detalle: ReservaFila[];
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
  selector: 'app-reporte-reservas',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './reservas.html',
  styleUrl: './reservas.scss',
})
export class ReporteReservasPage implements OnInit {
  // Logo y nombre de la tienda en el encabezado del reporte.
  protected readonly marca = inject(MarcaTienda);
  private readonly http = inject(HttpClient);

  protected readonly fechaDesde = signal(primerDiaMes());
  protected readonly fechaHasta = signal(hoy());
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly estado = signal('');
  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly datos = signal<ReporteReservas | null>(null);
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
    if (this.estado()) params['estado'] = this.estado();
    return params;
  }

  protected async buscar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(
        this.http.get<ReporteReservas>(`${environment.apiUrl}/reportes/reservas`, { params: this.params() }),
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
        this.http.get(`${environment.apiUrl}/reportes/reservas/exportar`, {
          params: { ...this.params(), formato },
          responseType: 'blob',
        }),
      );
      descargarArchivo(blob, `reporte_reservas.${formato === 'excel' ? 'xlsx' : 'csv'}`);
    } catch {
      this.error.set('No se pudo exportar el reporte.');
    } finally {
      this.exportando.set(false);
    }
  }
}
