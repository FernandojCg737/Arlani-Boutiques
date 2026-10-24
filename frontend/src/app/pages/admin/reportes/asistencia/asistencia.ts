import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MarcaTienda } from '../../../../services/marca-tienda';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ExportarReporte } from '../../../../components/reporte/exportar-reporte';
import { environment } from '../../../../../environments/environment';

interface AsistenciaFila {
  empleado_id: number;
  empleado_nombre: string;
  sucursal_nombre: string;
  fecha: string;
  hora_entrada: string | null;
  hora_salida: string | null;
  horas_conectado: number;
}

interface ReporteAsistencia {
  resumen: { empleados_activos: number; dias_con_actividad: number; promedio_horas_por_dia: number };
  detalle: AsistenciaFila[];
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

// CU16: reporte de asistencia derivado del historial de login/logout de la
// bitacora (CU17) -- no hay un modulo de fichaje/marcado de asistencia
// separado en el proyecto, asi que esto refleja presencia en el sistema,
// no un reloj checador fisico.
@Component({
  selector: 'app-reporte-asistencia',
  imports: [DatePipe, DecimalPipe, RouterLink, ExportarReporte],
  templateUrl: './asistencia.html',
  styleUrl: './asistencia.scss',
})
export class ReporteAsistenciaPage implements OnInit {
  // Exportar (PDF, Excel, CSV, HTML) o enviar por correo, con los filtros de la pantalla.
  protected readonly urlExportar = `${environment.apiUrl}/reportes/asistencia/exportar`;
  // Logo y nombre de la tienda en el encabezado del reporte.
  protected readonly marca = inject(MarcaTienda);
  private readonly http = inject(HttpClient);

  protected readonly fechaDesde = signal(hace30Dias());
  protected readonly fechaHasta = signal(hoy());
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly datos = signal<ReporteAsistencia | null>(null);
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
    const params: Record<string, string> = { fecha_desde: this.fechaDesde(), fecha_hasta: this.fechaHasta() };
    if (this.sucursalId()) params['sucursal_id'] = String(this.sucursalId());
    return params;
  }

  protected async buscar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const res = await firstValueFrom(
        this.http.get<ReporteAsistencia>(`${environment.apiUrl}/reportes/asistencia`, { params: this.params() }),
      );
      this.datos.set(res);
    } catch {
      this.error.set('No se pudo cargar el reporte.');
    } finally {
      this.loading.set(false);
    }
  }

}
