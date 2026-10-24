import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { mensajeError } from '../../services/plataforma';
import { AppChart } from '../chart/chart';
import { ExportarReporte } from './exportar-reporte';
import { TablaReporte, TablaReporteComponent } from './tabla-reporte';

interface Opcion {
  clave: string;
  etiqueta: string;
}

interface FuenteReporte {
  clave: string;
  etiqueta: string;
  descripcion: string;
  con_fechas: boolean;
  dimensiones: Opcion[];
  metricas: Opcion[];
  defecto: { agrupar: string[]; metricas: string[] };
}

function hoy(dias = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

// Reporte dinámico: el usuario elige qué datos, cómo agruparlos, qué medir y
// los filtros; el sistema arma la tabla y el gráfico, y se exporta o envía.
// ambito 'tienda' (CU07: su tienda; el SuperAdministrador, la elegida) o
// 'plataforma' (CU20: toda la plataforma SaaS).
@Component({
  selector: 'app-reporte-dinamico',
  imports: [AppChart, ExportarReporte, TablaReporteComponent],
  template: `
    <div class="dinamico">
      <section class="dinamico__panel">
        <span class="dinamico__etiqueta">1. ¿Qué datos?</span>
        <div class="dinamico__fuentes">
          @for (f of fuentes(); track f.clave) {
            <button type="button" [class.is-activa]="fuente()?.clave === f.clave" (click)="elegirFuente(f)">
              <strong>{{ f.etiqueta }}</strong>
              <small>{{ f.descripcion }}</small>
            </button>
          }
        </div>

        @if (fuente(); as f) {
          <div class="dinamico__fila">
            <label>
              <span class="dinamico__etiqueta">2. Agrupar por</span>
              <select [value]="agrupar1()" (change)="agrupar1.set($any($event.target).value)">
                @for (d of f.dimensiones; track d.clave) {
                  <option [value]="d.clave">{{ d.etiqueta }}</option>
                }
              </select>
            </label>
            <label>
              <span class="dinamico__etiqueta">y luego por (opcional)</span>
              <select [value]="agrupar2()" (change)="agrupar2.set($any($event.target).value)">
                <option value="">—</option>
                @for (d of f.dimensiones; track d.clave) {
                  @if (d.clave !== agrupar1()) {
                    <option [value]="d.clave">{{ d.etiqueta }}</option>
                  }
                }
              </select>
            </label>
            @if (f.con_fechas) {
              <label>
                <span class="dinamico__etiqueta">Desde</span>
                <input type="date" [value]="desde()" (change)="desde.set($any($event.target).value)" />
              </label>
              <label>
                <span class="dinamico__etiqueta">Hasta</span>
                <input type="date" [value]="hasta()" (change)="hasta.set($any($event.target).value)" />
              </label>
            }
            @if (ambito() === 'tienda' && sucursales().length) {
              <label>
                <span class="dinamico__etiqueta">Sucursal</span>
                <select [value]="filtro()" (change)="filtro.set($any($event.target).value)">
                  <option value="">Todas</option>
                  @for (s of sucursales(); track s.id) {
                    <option [value]="s.id">{{ s.nombre }}</option>
                  }
                </select>
              </label>
            }
            @if (ambito() === 'plataforma' && empresas().length) {
              <label>
                <span class="dinamico__etiqueta">Tienda</span>
                <select [value]="filtro()" (change)="filtro.set($any($event.target).value)">
                  <option value="">Todas</option>
                  @for (e of empresas(); track e.id) {
                    <option [value]="e.id">{{ e.nombre }}</option>
                  }
                </select>
              </label>
            }
          </div>

          <span class="dinamico__etiqueta">3. ¿Qué medir?</span>
          <div class="dinamico__metricas">
            @for (m of f.metricas; track m.clave) {
              <label>
                <input type="checkbox" [checked]="metricas().includes(m.clave)" (change)="alternarMetrica(m.clave)" />
                {{ m.etiqueta }}
              </label>
            }
          </div>

          <button type="button" class="dinamico__generar" [disabled]="cargando() || !metricas().length" (click)="generar()">
            {{ cargando() ? 'Generando…' : 'Generar reporte' }}
          </button>
        }
        @if (error()) {
          <p class="dinamico__error">{{ error() }}</p>
        }
      </section>

      @if (tabla(); as t) {
        <section class="dinamico__resultado">
          <header>
            <div>
              <h2>{{ t.titulo }}</h2>
              @if (t.subtitulo) {
                <p>{{ t.subtitulo }}</p>
              }
            </div>
            <app-exportar-reporte [tabla]="t" />
          </header>
          @if (t.filas.length) {
            <div class="dinamico__grafico">
              <app-chart [type]="tipoGrafico()" [labels]="etiquetas()" [data]="valores()" [label]="t.columnas[columnasDims()]?.etiqueta ?? ''" />
            </div>
          }
          <app-tabla-reporte [tabla]="t" />
        </section>
      }
    </div>
  `,
  styles: `
    .dinamico {
      display: grid;
      gap: 20px;
    }
    .dinamico__panel,
    .dinamico__resultado {
      padding: 20px;
      background: #fff;
      border: 1px solid #e5e5e5;
    }
    .dinamico__etiqueta {
      display: block;
      margin: 0 0 8px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #777;
    }
    .dinamico__fuentes {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 8px;
      margin-bottom: 18px;
    }
    .dinamico__fuentes button {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 12px;
      border: 1px solid #ddd;
      background: #fff;
      text-align: left;
      font: inherit;
      cursor: pointer;
    }
    .dinamico__fuentes button.is-activa {
      border-color: #1f2a44;
      box-shadow: inset 0 0 0 1px #1f2a44;
    }
    .dinamico__fuentes strong {
      font-size: 14px;
      color: #1f2a44;
    }
    .dinamico__fuentes small {
      font-size: 12px;
      color: #777;
    }
    .dinamico__fila {
      display: flex;
      flex-wrap: wrap;
      gap: 12px 16px;
      margin-bottom: 16px;
    }
    .dinamico__fila select,
    .dinamico__fila input {
      min-width: 160px;
      padding: 8px 10px;
      border: 1px solid #ddd;
      background: #fff;
      font: inherit;
      font-size: 13px;
    }
    .dinamico__metricas {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 18px;
      margin-bottom: 16px;
      font-size: 13px;
    }
    .dinamico__generar {
      border: none;
      background: #1f2a44;
      color: #fff;
      padding: 11px 20px;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: pointer;
    }
    .dinamico__generar:disabled {
      opacity: 0.5;
    }
    .dinamico__error {
      margin: 10px 0 0;
      color: #b3261e;
      font-size: 13px;
    }
    .dinamico__resultado header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
    }
    .dinamico__resultado h2 {
      margin: 0;
      font-size: 17px;
      color: #1f2a44;
    }
    .dinamico__resultado header p {
      margin: 4px 0 0;
      font-size: 13px;
      color: #777;
    }
    .dinamico__grafico {
      margin-bottom: 16px;
    }
  `,
})
export class ReporteDinamico implements OnInit {
  private readonly http = inject(HttpClient);

  readonly ambito = input<'tienda' | 'plataforma'>('tienda');
  readonly sucursales = input<{ id: number; nombre: string }[]>([]);
  readonly empresas = input<{ id: number; nombre: string }[]>([]);

  protected readonly fuentes = signal<FuenteReporte[]>([]);
  protected readonly fuente = signal<FuenteReporte | null>(null);
  protected readonly agrupar1 = signal('');
  protected readonly agrupar2 = signal('');
  protected readonly metricas = signal<string[]>([]);
  protected readonly desde = signal(hoy(-180));
  protected readonly hasta = signal(hoy());
  protected readonly filtro = signal('');
  protected readonly tabla = signal<TablaReporte | null>(null);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');

  private get base(): string {
    return `${environment.apiUrl}/${this.ambito() === 'plataforma' ? 'reportes-saas' : 'reportes'}/dinamico`;
  }

  // Columnas de agrupación (las primeras) y la primera medida, para el gráfico.
  protected readonly columnasDims = computed(() => this.tabla()?.columnas.filter((c) => c.clave.startsWith('d')).length ?? 0);
  protected readonly etiquetas = computed(() => {
    const t = this.tabla();
    if (!t) return [];
    const dims = t.columnas.filter((c) => c.clave.startsWith('d')).map((c) => c.clave);
    return t.filas.slice(0, 40).map((f) => dims.map((d) => String(f[d] ?? '')).join(' · '));
  });
  protected readonly valores = computed(() => {
    const t = this.tabla();
    const medida = t?.columnas[this.columnasDims()];
    return t && medida ? t.filas.slice(0, 40).map((f) => Number(f[medida.clave] ?? 0)) : [];
  });
  protected readonly tipoGrafico = computed(() => (['dia', 'semana', 'mes'].includes(this.agrupar1()) ? 'line' : 'bar'));

  async ngOnInit(): Promise<void> {
    try {
      const fs = await firstValueFrom(this.http.get<FuenteReporte[]>(`${this.base}/fuentes`));
      this.fuentes.set(fs);
      if (fs.length) this.elegirFuente(fs[0]);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudieron cargar las fuentes de datos.'));
    }
  }

  protected elegirFuente(f: FuenteReporte): void {
    this.fuente.set(f);
    this.agrupar1.set(f.defecto.agrupar[0] ?? f.dimensiones[0]?.clave ?? '');
    this.agrupar2.set('');
    this.metricas.set([...f.defecto.metricas]);
    this.tabla.set(null);
  }

  protected alternarMetrica(clave: string): void {
    this.metricas.update((ms) => (ms.includes(clave) ? ms.filter((m) => m !== clave) : [...ms, clave]));
  }

  protected async generar(): Promise<void> {
    const f = this.fuente();
    if (!f) return;
    this.cargando.set(true);
    this.error.set('');
    const filtro = this.filtro() ? Number(this.filtro()) : null;
    try {
      this.tabla.set(
        await firstValueFrom(
          this.http.post<TablaReporte>(this.base, {
            fuente: f.clave,
            agrupar: [this.agrupar1(), this.agrupar2()].filter(Boolean),
            metricas: this.metricas(),
            desde: f.con_fechas ? this.desde() || null : null,
            hasta: f.con_fechas ? this.hasta() || null : null,
            sucursal_id: this.ambito() === 'tienda' ? filtro : null,
            empresa_id: this.ambito() === 'plataforma' ? filtro : null,
          }),
        ),
      );
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo generar el reporte.'));
    } finally {
      this.cargando.set(false);
    }
  }
}
