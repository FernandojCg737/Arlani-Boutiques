import { HttpClient } from '@angular/common/http';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { AppChart } from '../../../components/chart/chart';
import { ExportarReporte } from '../../../components/reporte/exportar-reporte';
import { TablaReporte, TablaReporteComponent } from '../../../components/reporte/tabla-reporte';
import { mensajeError } from '../../../services/plataforma';
import { callar, hablar, soportaVoz } from '../../../services/voz';

interface Estado {
  disponible: boolean;
  plan: string | null;
  sugerencias: string[];
}

interface Interpretacion {
  intencion: string;
  confianza: number;
  reporte?: string;
  filtros?: string[];
}

interface Respuesta {
  entendido: boolean;
  mensaje?: string;
  sugerencias?: string[];
  interpretacion: Interpretacion;
  tabla?: TablaReporte;
  grafico?: 'bar' | 'line' | 'doughnut';
  narrativa?: string;
}

// Web Speech API: Chrome y Edge la exponen con prefijo.
type Reconocedor = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
};

function crearReconocedor(): Reconocedor | null {
  const w = window as unknown as Record<string, new () => Reconocedor>;
  const Clase = w['SpeechRecognition'] ?? w['webkitSpeechRecognition'];
  return Clase ? new Clase() : null;
}

// CU17: el usuario pide un reporte hablando o escribiendo; el modelo del CU18
// entiende qué reporte es y el sistema lo arma con los datos de su tienda.
@Component({
  selector: 'app-reporte-voz',
  imports: [AppChart, ExportarReporte, TablaReporteComponent],
  template: `
    <div class="voz-page">
      <h1 class="voz-titulo">{{ esSaas ? 'Reportes del SaaS por voz' : 'Reportes por voz' }}</h1>
      <p class="voz-intro">
        @if (esSaas) {
          Pide reportes de toda la plataforma (suscripciones, comisiones, ventas de las tiendas, planes) como se los pedirías a
          una persona. Los entiende el modelo de reportes del SaaS (CU18).
        } @else {
          Pide el reporte como se lo pedirías a una persona. Lo entiende un modelo entrenado para tu tienda.
        }
      </p>

      @if (estado(); as e) {
        @if (!e.disponible) {
          <div class="voz-plan">
            <strong>Disponible en el plan Profesional</strong>
            <p>La tienda tiene el plan {{ e.plan ?? 'actual' }}. Con el plan Profesional se pueden pedir reportes por voz o texto (se cambia en Mi suscripción).</p>
          </div>
        } @else {
          <section class="voz-pedido">
            <div class="voz-entrada">
              @if (soportaVoz) {
                <button
                  type="button"
                  class="voz-mic"
                  [class.is-escuchando]="escuchando()"
                  [attr.aria-pressed]="escuchando()"
                  [attr.aria-label]="escuchando() ? 'Dejar de escuchar' : 'Hablar'"
                  (click)="alternarMic()"
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z" />
                  </svg>
                </button>
              }
              <input
                type="text"
                maxlength="300"
                [placeholder]="escuchando() ? 'Te escucho…' : esSaas ? 'Ej.: ingresos por suscripciones de los últimos tres meses' : 'Ej.: ventas de septiembre agrupadas por sucursal'"
                [value]="texto()"
                (input)="texto.set($any($event.target).value)"
                (keydown.enter)="pedir(false)"
              />
              <button type="button" class="voz-generar" [disabled]="cargando() || texto().trim().length < 2" (click)="pedir(false)">
                {{ cargando() ? 'Generando…' : 'Generar' }}
              </button>
            </div>
            @if (!soportaVoz) {
              <p class="voz-nota">Este navegador no reconoce la voz: escribe el pedido (en Chrome o Edge puedes hablar).</p>
            } @else if (escuchando()) {
              <p class="voz-nota">Habla ahora. Al terminar la frase se genera el reporte.</p>
            }
            <div class="voz-sugerencias">
              @for (s of sugerencias(); track s) {
                <button type="button" (click)="usarSugerencia(s)">{{ s }}</button>
              }
            </div>
            @if (error()) {
              <p class="voz-error">{{ error() }}</p>
            }
          </section>

          @if (respuesta(); as r) {
            @if (!r.entendido) {
              <section class="voz-no">
                <strong>{{ r.mensaje }}</strong>
              </section>
            } @else if (r.tabla; as t) {
              <section class="voz-resultado">
                <header>
                  <div>
                    <h2>{{ r.interpretacion.reporte }}</h2>
                    <div class="voz-chips">
                      <span class="voz-chip is-ia">Confianza {{ porcentaje(r.interpretacion.confianza) }}</span>
                      @for (f of r.interpretacion.filtros ?? []; track f) {
                        <span class="voz-chip">{{ f }}</span>
                      }
                    </div>
                  </div>
                  <app-exportar-reporte [tabla]="t" />
                </header>
                @if (r.narrativa) {
                  <div class="voz-narrativa">
                    <p>{{ r.narrativa }}</p>
                    @if (soportaLectura) {
                      <button type="button" (click)="leer(r.narrativa)">{{ leyendo() ? 'Detener' : 'Escuchar' }}</button>
                    }
                  </div>
                }
                @if (t.filas.length) {
                  <div class="voz-grafico">
                    <app-chart [type]="r.grafico ?? 'bar'" [labels]="etiquetas()" [data]="valores()" [label]="medida()" />
                  </div>
                }
                <app-tabla-reporte [tabla]="t" />
              </section>
            }
          }
        }
      } @else if (error()) {
        <p class="voz-error">{{ error() }}</p>
      }
    </div>
  `,
  styles: `
    .voz-page {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }
    .voz-titulo {
      margin: 0 0 4px;
      font-size: 26px;
      font-weight: 800;
      text-transform: uppercase;
      color: #1f2a44;
    }
    .voz-intro {
      margin: 0 0 18px;
      color: #666;
      font-size: 14px;
    }
    .voz-plan,
    .voz-pedido,
    .voz-no,
    .voz-resultado {
      padding: 20px;
      background: #fff;
      border: 1px solid #e5e5e5;
      margin-bottom: 20px;
    }
    .voz-plan strong {
      color: #1f2a44;
    }
    .voz-plan p {
      margin: 6px 0 0;
      font-size: 14px;
      color: #555;
    }
    .voz-entrada {
      display: flex;
      gap: 10px;
      align-items: stretch;
    }
    .voz-entrada input {
      flex: 1;
      min-width: 0;
      padding: 12px 14px;
      border: 1px solid #ddd;
      font: inherit;
      font-size: 15px;
    }
    .voz-mic {
      flex: none;
      width: 48px;
      border: 1px solid #1f2a44;
      background: #fff;
      color: #1f2a44;
      cursor: pointer;
      display: grid;
      place-items: center;
    }
    .voz-mic svg {
      width: 22px;
      height: 22px;
      fill: currentColor;
    }
    .voz-mic.is-escuchando {
      background: #c4503d;
      border-color: #c4503d;
      color: #fff;
      animation: voz-pulso 1.2s ease-in-out infinite;
    }
    @keyframes voz-pulso {
      50% {
        box-shadow: 0 0 0 6px rgba(196, 80, 61, 0.2);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .voz-mic.is-escuchando {
        animation: none;
      }
    }
    .voz-generar {
      flex: none;
      border: none;
      background: #1f2a44;
      color: #fff;
      padding: 0 22px;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: pointer;
    }
    .voz-generar:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .voz-nota {
      margin: 8px 0 0;
      font-size: 13px;
      color: #777;
    }
    .voz-sugerencias {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }
    .voz-sugerencias button {
      border: 1px solid #ddd;
      background: #faf8f7;
      padding: 6px 12px;
      font: inherit;
      font-size: 13px;
      color: #3e4c6d;
      cursor: pointer;
    }
    .voz-sugerencias button:hover {
      border-color: #3e4c6d;
    }
    .voz-error {
      margin: 10px 0 0;
      color: #b3261e;
      font-size: 13px;
    }
    .voz-no strong {
      color: #1f2a44;
      font-size: 14px;
    }
    .voz-resultado header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
    }
    .voz-resultado h2 {
      margin: 0 0 8px;
      font-size: 17px;
      color: #1f2a44;
    }
    .voz-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .voz-chip {
      padding: 3px 9px;
      background: #f1f0ef;
      font-size: 12px;
      color: #555;
    }
    .voz-chip.is-ia {
      background: #1f2a44;
      color: #fff;
    }
    .voz-narrativa {
      display: flex;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      margin-bottom: 16px;
      border-left: 3px solid #c4503d;
      background: #faf8f7;
    }
    .voz-narrativa p {
      flex: 1;
      margin: 0;
      font-size: 14px;
      color: #333;
    }
    .voz-narrativa button {
      flex: none;
      border: 1px solid #1f2a44;
      background: #fff;
      padding: 6px 12px;
      font: inherit;
      font-size: 12px;
      cursor: pointer;
    }
    .voz-grafico {
      max-width: 820px;
      margin-bottom: 16px;
    }
    @media (max-width: 600px) {
      .voz-entrada {
        flex-wrap: wrap;
      }
      .voz-entrada input {
        flex-basis: calc(100% - 58px);
      }
      .voz-generar {
        width: 100%;
        padding: 12px;
      }
    }
  `,
})
export class AdminReporteVoz implements OnInit, OnDestroy {
  private readonly http = inject(HttpClient);
  // data: { ambito: 'saas' }: los reportes de toda la plataforma (SuperAdministrador).
  protected readonly esSaas = inject(ActivatedRoute).snapshot.data['ambito'] === 'saas';
  private readonly base = `${environment.apiUrl}/reportes-voz${this.esSaas ? '/saas' : ''}`;
  private reconocedor: Reconocedor | null = null;

  protected readonly soportaVoz = !!crearReconocedor();
  protected readonly soportaLectura = soportaVoz;

  protected readonly estado = signal<Estado | null>(null);
  protected readonly texto = signal('');
  protected readonly escuchando = signal(false);
  protected readonly leyendo = signal(false);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');
  protected readonly respuesta = signal<Respuesta | null>(null);

  protected readonly sugerencias = computed(() => this.respuesta()?.sugerencias ?? this.estado()?.sugerencias ?? []);

  // Primera columna (lo agrupado) contra la primera medida, para el gráfico.
  private readonly dims = computed(() => {
    const t = this.respuesta()?.tabla;
    return t ? Math.max(1, t.columnas.findIndex((c) => c.tipo === 'numero' || c.tipo === 'moneda')) : 1;
  });
  protected readonly etiquetas = computed(() => {
    const t = this.respuesta()?.tabla;
    if (!t) return [];
    const claves = t.columnas.slice(0, this.dims()).map((c) => c.clave);
    return t.filas.slice(0, 40).map((f) => claves.map((k) => String(f[k] ?? '')).join(' · '));
  });
  protected readonly valores = computed(() => {
    const t = this.respuesta()?.tabla;
    const m = t?.columnas[this.dims()];
    return t && m ? t.filas.slice(0, 40).map((f) => Number(f[m.clave] ?? 0)) : [];
  });
  protected readonly medida = computed(() => this.respuesta()?.tabla?.columnas[this.dims()]?.etiqueta ?? '');

  async ngOnInit(): Promise<void> {
    try {
      this.estado.set(await firstValueFrom(this.http.get<Estado>(`${this.base}/estado`)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo abrir los reportes por voz.'));
    }
  }

  ngOnDestroy(): void {
    this.reconocedor?.stop();
    callar();
  }

  protected porcentaje(v: number): string {
    return `${Math.round(v * 100)}%`;
  }

  protected usarSugerencia(s: string): void {
    this.texto.set(s);
    void this.pedir(false);
  }

  protected alternarMic(): void {
    if (this.escuchando()) {
      this.reconocedor?.stop();
      return;
    }
    const r = crearReconocedor();
    if (!r) return;
    r.lang = 'es-BO';
    r.interimResults = true;
    r.continuous = false;
    let final = '';
    r.onresult = (e) => {
      let parcial = '';
      final = '';
      for (const res of Array.from(e.results)) {
        if (res.isFinal) final += res[0].transcript;
        else parcial += res[0].transcript;
      }
      this.texto.set((final || parcial).trim());
    };
    r.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        this.error.set('El navegador no dejó usar el micrófono. Dale permiso y vuelve a intentar.');
      } else if (e.error === 'language-not-supported' && r.lang !== 'es-ES') {
        r.lang = 'es-ES';
      } else if (e.error !== 'no-speech' && e.error !== 'aborted') {
        this.error.set('No se pudo reconocer la voz. Prueba de nuevo o escribe el pedido.');
      }
    };
    r.onend = () => {
      this.escuchando.set(false);
      this.reconocedor = null;
      if (final.trim().length >= 2) void this.pedir(true);
    };
    this.error.set('');
    this.texto.set('');
    this.reconocedor = r;
    this.escuchando.set(true);
    r.start();
  }

  protected leer(texto: string): void {
    if (this.leyendo()) {
      callar();
      this.leyendo.set(false);
      return;
    }
    this.leyendo.set(true);
    void hablar(texto, () => this.leyendo.set(false));
  }

  protected async pedir(porVoz: boolean): Promise<void> {
    const texto = this.texto().trim();
    if (texto.length < 2 || this.cargando()) return;
    this.cargando.set(true);
    this.error.set('');
    callar();
    this.leyendo.set(false);
    try {
      const r = await firstValueFrom(this.http.post<Respuesta>(this.base, { texto, por_voz: porVoz }));
      this.respuesta.set(r);
      // Si lo pidió hablando, la respuesta también se dice en voz alta.
      const dicho = r.entendido ? r.narrativa : r.mensaje;
      if (porVoz && dicho && this.soportaLectura) this.leer(dicho);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo generar el reporte.'));
    } finally {
      this.cargando.set(false);
    }
  }
}
