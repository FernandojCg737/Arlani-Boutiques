import { DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { AppChart } from '../../../components/chart/chart';
import { ExportarReporte } from '../../../components/reporte/exportar-reporte';
import { ReporteDinamico } from '../../../components/reporte/reporte-dinamico';
import { TablaReporte, TablaReporteComponent } from '../../../components/reporte/tabla-reporte';
import { PlataformaApi, mensajeError } from '../../../services/plataforma';

type Vista = 'resumen' | 'suscripciones' | 'comisiones' | 'tiendas' | 'planes' | 'vencimientos' | 'dinamico';

interface ResumenSaas {
  ingreso_total: string;
  ingreso_suscripciones: string;
  pagos_suscripcion: number;
  ingreso_comisiones: string;
  ventas_con_comision: number;
  gmv: string;
  ventas_tiendas: number;
  mrr: string;
  empresas_activas: number;
  empresas_prueba: number;
  empresas_suspendidas: number;
  empresas_total: number;
  por_mes: { mes: string; suscripciones: string; comisiones: string; total: string }[];
  por_plan: { plan: string; tiendas: number; mrr: string }[];
}

function fecha(dias = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

// CU20 Gestionar reportes de la plataforma (SaaS): lo que gana Arlani
// (suscripciones + comisiones por ventas), MRR, tiendas, planes y
// vencimientos; reportes fijos y uno dinámico, exportables (PDF, Excel, CSV,
// HTML) y enviables por correo.
@Component({
  selector: 'app-reportes-saas',
  imports: [DecimalPipe, AppChart, ExportarReporte, ReporteDinamico, TablaReporteComponent],
  templateUrl: './reportes-saas.html',
  styleUrls: ['../../admin/ventas/ventas.scss', './reportes-saas.scss'],
})
export class ReportesSaas implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly plataforma = inject(PlataformaApi);
  private readonly api = `${environment.apiUrl}/reportes-saas`;

  protected readonly vistas: { clave: Vista; etiqueta: string }[] = [
    { clave: 'resumen', etiqueta: 'Resumen' },
    { clave: 'suscripciones', etiqueta: 'Suscripciones' },
    { clave: 'comisiones', etiqueta: 'Comisiones' },
    { clave: 'tiendas', etiqueta: 'Tiendas' },
    { clave: 'planes', etiqueta: 'Planes' },
    { clave: 'vencimientos', etiqueta: 'Por vencer' },
    { clave: 'dinamico', etiqueta: 'Reporte dinámico' },
  ];
  protected readonly vista = signal<Vista>('resumen');
  protected readonly desde = signal(fecha(-180));
  protected readonly hasta = signal(fecha());
  protected readonly resumen = signal<ResumenSaas | null>(null);
  protected readonly tabla = signal<TablaReporte | null>(null);
  protected readonly empresas = signal<{ id: number; nombre: string }[]>([]);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');

  protected readonly etiquetasMes = computed(() =>
    (this.resumen()?.por_mes ?? []).map((m) => `${MESES[Number(m.mes.slice(5)) - 1]} ${m.mes.slice(2, 4)}`),
  );
  protected readonly seriesMes = computed(() => {
    const r = this.resumen()?.por_mes ?? [];
    return [
      { label: 'Suscripciones', data: r.map((m) => Number(m.suscripciones)) },
      { label: 'Comisiones', data: r.map((m) => Number(m.comisiones)) },
    ];
  });
  // El resumen también se exporta: ingresos de Arlani por mes.
  protected readonly tablaResumen = computed<TablaReporte | null>(() => {
    const r = this.resumen();
    if (!r) return null;
    return {
      titulo: 'Ingresos de Arlani por mes',
      subtitulo: `Del ${this.desde()} al ${this.hasta()} · MRR Bs ${r.mrr} · ${r.empresas_activas} tiendas activas`,
      columnas: [
        { clave: 'mes', etiqueta: 'Mes', tipo: 'texto' },
        { clave: 'suscripciones', etiqueta: 'Suscripciones (Bs)', tipo: 'moneda' },
        { clave: 'comisiones', etiqueta: 'Comisiones (Bs)', tipo: 'moneda' },
        { clave: 'total', etiqueta: 'Total (Bs)', tipo: 'moneda' },
      ],
      filas: r.por_mes,
      totales: {
        mes: 'Total',
        suscripciones: r.ingreso_suscripciones,
        comisiones: r.ingreso_comisiones,
        total: r.ingreso_total,
      },
    };
  });

  ngOnInit(): void {
    void this.cargar();
    void this.plataforma.empresas().then(
      (es) => this.empresas.set(es.map((e) => ({ id: e.id, nombre: e.nombre }))),
      () => undefined,
    );
  }

  protected cambiarVista(v: Vista): void {
    this.vista.set(v);
    if (v !== 'dinamico') void this.cargar();
  }

  protected async cargar(): Promise<void> {
    const v = this.vista();
    if (v === 'dinamico') return;
    this.cargando.set(true);
    this.error.set('');
    const params = { desde: this.desde(), hasta: this.hasta() };
    try {
      if (v === 'resumen') {
        this.resumen.set(await firstValueFrom(this.http.get<ResumenSaas>(`${this.api}/resumen`, { params })));
      } else {
        this.tabla.set(await firstValueFrom(this.http.get<TablaReporte>(`${this.api}/tabla/${v}`, { params })));
      }
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo cargar el reporte.'));
    } finally {
      this.cargando.set(false);
    }
  }
}
