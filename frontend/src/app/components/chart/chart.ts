import { Component, ElementRef, OnDestroy, effect, input, viewChild } from '@angular/core';
import { Chart, ChartConfiguration, ChartType, registerables } from 'chart.js';

Chart.register(...registerables);

const BRAND_DARK = '#203C40';
const PALETTE = ['#203C40', '#7a9b95', '#c9a15a', '#a8554b', '#5a7a9b', '#8a8a5a', '#2b2b2b', '#b3261e'];

// Wrapper minimo sobre Chart.js: el proyecto no usa librerias de UI pesadas
// en ningun lado (todo es SCSS a mano), asi que en vez de sumar un wrapper
// de Angular para graficos (ng2-charts) se maneja Chart.js directo con un
// <canvas> y se reconstruye el grafico cada vez que cambian los inputs.
@Component({
  selector: 'app-chart',
  imports: [],
  template: `<div class="chart-wrap"><canvas #canvas></canvas></div>`,
  styles: [
    `
      .chart-wrap {
        position: relative;
        width: 100%;
        height: 260px;
      }
      canvas {
        width: 100% !important;
        height: 100% !important;
      }
    `,
  ],
})
export class AppChart implements OnDestroy {
  readonly type = input.required<ChartType>();
  readonly labels = input.required<string[]>();
  readonly data = input.required<number[]>();
  readonly label = input<string>('');
  // Varias series (p. ej. suscripciones y comisiones por mes): barras apiladas.
  readonly series = input<{ label: string; data: number[] }[]>([]);

  private readonly canvasRef = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private chart?: Chart;

  constructor() {
    effect(() => {
      const tipo = this.type();
      const labels = this.labels();
      const data = this.data();
      const label = this.label();
      const series = this.series();
      queueMicrotask(() => this.render(tipo, labels, data, label, series));
    });
  }

  private render(
    tipo: ChartType,
    labels: string[],
    data: number[],
    label: string,
    series: { label: string; data: number[] }[],
  ): void {
    const ctx = this.canvasRef().nativeElement.getContext('2d');
    if (!ctx) return;

    this.chart?.destroy();

    const esCircular = tipo === 'pie' || tipo === 'doughnut';
    const apiladas = series.length > 0 && !esCircular;
    const config: ChartConfiguration = {
      type: tipo,
      data: {
        labels,
        datasets: apiladas
          ? series.map((s, i) => ({
              label: s.label,
              data: s.data,
              backgroundColor: PALETTE[i % PALETTE.length],
              borderRadius: 3,
            }))
          : [
          {
            label,
            data,
            backgroundColor: esCircular ? PALETTE : BRAND_DARK,
            borderColor: esCircular ? '#fff' : BRAND_DARK,
            borderWidth: esCircular ? 2 : 0,
            borderRadius: tipo === 'bar' ? 3 : 0,
            tension: tipo === 'line' ? 0.3 : 0,
            fill: tipo === 'line',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: esCircular || apiladas, position: 'bottom', labels: { font: { size: 11 } } },
        },
        scales: esCircular
          ? {}
          : {
              y: { beginAtZero: true, stacked: apiladas, ticks: { font: { size: 11 } } },
              x: { stacked: apiladas, ticks: { font: { size: 11 } } },
            },
      },
    };

    this.chart = new Chart(ctx, config);
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }
}
