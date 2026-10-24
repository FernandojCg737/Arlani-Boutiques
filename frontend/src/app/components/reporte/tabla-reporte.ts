import { Component, input } from '@angular/core';

export interface ColumnaReporte {
  clave: string;
  etiqueta: string;
  tipo: 'texto' | 'numero' | 'moneda' | 'fecha';
}

// Un reporte como lo devuelve el backend (estático o dinámico): se muestra,
// se exporta y se envía por correo con la misma forma.
export interface TablaReporte {
  titulo: string;
  subtitulo: string | null;
  columnas: ColumnaReporte[];
  filas: Record<string, unknown>[];
  totales: Record<string, unknown> | null;
}

const BS = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const NUM = new Intl.NumberFormat('es-BO', { maximumFractionDigits: 2 });

export function valorReporte(v: unknown, tipo: ColumnaReporte['tipo']): string {
  if (v === null || v === undefined || v === '') return '';
  if (tipo === 'moneda') return BS.format(Number(v));
  if (tipo === 'numero' && !Number.isNaN(Number(v))) return NUM.format(Number(v));
  return String(v);
}

@Component({
  selector: 'app-tabla-reporte',
  template: `
    <div class="tabla-reporte">
      <table>
        <thead>
          <tr>
            @for (c of tabla().columnas; track c.clave) {
              <th [class.num]="c.tipo === 'numero' || c.tipo === 'moneda'">{{ c.etiqueta }}</th>
            }
          </tr>
        </thead>
        <tbody>
          @for (f of tabla().filas; track $index) {
            <tr>
              @for (c of tabla().columnas; track c.clave) {
                <td [class.num]="c.tipo === 'numero' || c.tipo === 'moneda'">{{ valor(f[c.clave], c.tipo) }}</td>
              }
            </tr>
          } @empty {
            <tr>
              <td class="vacio" [attr.colspan]="tabla().columnas.length">No hay datos para estos filtros.</td>
            </tr>
          }
        </tbody>
        @if (tabla().totales && tabla().filas.length) {
          <tfoot>
            <tr>
              @for (c of tabla().columnas; track c.clave; let i = $index) {
                <td [class.num]="c.tipo === 'numero' || c.tipo === 'moneda'">
                  {{ valor(tabla().totales![c.clave] ?? (i === 0 ? 'Total' : ''), c.tipo) }}
                </td>
              }
            </tr>
          </tfoot>
        }
      </table>
    </div>
  `,
  styles: `
    .tabla-reporte {
      overflow-x: auto;
      background: #fff;
      border: 1px solid #e5e5e5;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th {
      padding: 10px 12px;
      text-align: left;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: #777;
      border-bottom: 1px solid #e5e5e5;
      white-space: nowrap;
    }
    td {
      padding: 9px 12px;
      border-bottom: 1px solid #f0f0f0;
    }
    .num {
      text-align: right;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    tfoot td {
      font-weight: 800;
      border-top: 2px solid #1f2a44;
      border-bottom: none;
    }
    .vacio {
      padding: 24px;
      text-align: center;
      color: #888;
    }
  `,
})
export class TablaReporteComponent {
  readonly tabla = input.required<TablaReporte>();
  protected readonly valor = valorReporte;
}
