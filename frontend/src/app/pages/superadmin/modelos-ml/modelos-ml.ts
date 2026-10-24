import { DatePipe, DecimalPipe, PercentPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { AppChart } from '../../../components/chart/chart';
import { PlataformaApi, mensajeError } from '../../../services/plataforma';

interface Comparacion {
  representacion: string;
  algoritmo: string;
  accuracy: number;
  f1: number;
  f1_cv: number;
  // Frases escritas a mano con otras palabras (no se usan para entrenar).
  f1_parafrasis?: number;
  puntaje?: number;
}

interface Metricas extends Comparacion {
  precision: number;
  recall: number;
  clases: string[];
  por_clase: { clase: string; precision: number; recall: number; f1: number; soporte: number }[];
  matriz_confusion: number[][];
  n_entrenamiento: number;
  n_prueba: number;
  n_parafrasis?: number;
  vocabulario: number;
}

interface Modelo {
  tarea: 'reportes' | 'chatbot';
  // El chatbot tiene uno general (null) y uno por tienda.
  empresa_id: number | null;
  nombre: string;
  activo: {
    version: number;
    algoritmo: string;
    representacion: string;
    n_ejemplos: number;
    metricas: Metricas;
    comparacion: Comparacion[];
    entrenado_en: string;
    entrenado_por: string | null;
  };
  historial: { version: number; algoritmo: string; representacion: string; f1: number; accuracy: number; entrenado_en: string; activo: boolean }[];
}

interface Prueba {
  normalizado: string;
  tokens: string[];
  sin_stopwords: string[];
  lemas: string[];
  vector: { termino: string; peso: number }[];
  intencion: string;
  confianza: number;
  alternativas: { intencion: string; probabilidad: number }[];
}

interface Segmentos {
  k: number;
  silueta: number;
  siluetas: { k: number; silueta: number; inercia: number }[];
  segmentos: { segmento: string; clientes: number; recencia_dias: number; compras: number; monto: number }[];
  clientes: { cliente: string; compras: number; monto: number; ultima_compra: string; segmento: string }[];
  clientes_analizados: number;
  version: number;
}

// Recomendador de prendas de una tienda (híbrido contenido + KNN colaborativo).
interface FilaRecom {
  modelo: string;
  acierto: number;
  mrr: number;
}

interface Recomendador {
  activo: {
    version: number;
    algoritmo: string;
    entrenado_en: string;
    entrenado_por: string | null;
    metricas: {
      k: number;
      acierto: number;
      mrr: number;
      azar: number;
      referencia: FilaRecom;
      n_productos: number;
      n_clientes: number;
      n_ventas: number;
      n_vistas: number;
      n_pares_prueba: number;
      vecinos: number;
    };
    comparacion: FilaRecom[];
  };
  historial: { version: number; algoritmo: string; acierto: number; mrr: number; entrenado_en: string; activo: boolean }[];
  productos: { id: number; nombre: string }[];
}

interface Sugerida {
  producto_id: number;
  nombre: string;
  categoria: string;
  precio: number;
  similitud: number;
}

type Vista = 'reportes' | 'chatbot' | 'recomendaciones' | 'segmentos';
type Clasificador = 'reportes' | 'chatbot';

const EJEMPLOS: Record<'reportes' | 'chatbot', string[]> = {
  reportes: [
    'Mostrame las ventas de septiembre agrupadas por sucursal',
    '¿Cuáles fueron los diez productos más vendidos este mes?',
    'Generá un gráfico de ventas por semana',
    'Mostrame los productos con menor existencia',
  ],
  chatbot: ['¿A qué hora abren el sábado?', '¿Tienen la chaqueta de cuero en talla L?', '¿Puedo pagar con QR?', '¿Qué me recomiendas para una boda?'],
};

// CU18 Gestionar modelos de ML: los clasificadores de intenciones (reportes
// por voz del CU17 y chatbot) con su pipeline de 6 pasos, la comparación de
// modelos y sus métricas; y la segmentación de clientes con K-Means.
@Component({
  selector: 'app-modelos-ml',
  imports: [DatePipe, DecimalPipe, PercentPipe, RouterLink, AppChart],
  templateUrl: './modelos-ml.html',
  styleUrls: ['../../admin/ventas/ventas.scss', './modelos-ml.scss'],
})
export class ModelosMl implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly plataforma = inject(PlataformaApi);
  private readonly api = `${environment.apiUrl}/modelos-ml`;

  protected readonly pasos = [
    { n: 1, nombre: 'Normalización', detalle: 'minúsculas, sin tildes ni signos, números unificados' },
    { n: 2, nombre: 'Tokenización', detalle: 'el texto se parte en palabras' },
    { n: 3, nombre: 'Stopwords', detalle: 'se quitan las palabras vacías del español' },
    { n: 4, nombre: 'Lematización', detalle: 'cada palabra a su forma base' },
    { n: 5, nombre: 'BoW / TF-IDF / embeddings', detalle: 'las palabras (o su significado) se convierten en números' },
    { n: 6, nombre: 'Modelo', detalle: 'Regresión logística, Naive Bayes, KNN o Árbol de decisión' },
  ];

  protected readonly vista = signal<Vista>('reportes');
  protected readonly modelos = signal<Modelo[]>([]);
  protected readonly cargando = signal(true);
  protected readonly entrenando = signal(false);
  protected readonly error = signal('');
  protected readonly frase = signal(EJEMPLOS.reportes[0]);
  protected readonly prueba = signal<Prueba | null>(null);
  protected readonly probando = signal(false);
  protected readonly datos = signal<{ total: number; por_intencion: { intencion: string; ejemplos: number }[]; muestra: { texto: string; intencion: string }[] } | null>(null);

  protected readonly empresas = signal<{ id: number; nombre: string }[]>([]);
  protected readonly empresaId = signal<number | null>(null);
  protected readonly segmentos = signal<Segmentos | null>(null);
  protected readonly segmentando = signal(false);

  protected readonly lenguaje = signal<{
    habilitado: boolean;
    modo: 'remoto' | 'local' | 'apagado';
    disponible: boolean;
    nombre: string;
    dimensiones: number;
  } | null>(null);
  protected readonly recom = signal<Recomendador | null>(null);
  protected readonly recomCargando = signal(false);
  protected readonly recomProducto = signal<number | null>(null);
  protected readonly recomPrueba = signal<Sugerida[] | null>(null);

  private get esClasificador(): boolean {
    return this.vista() === 'reportes' || this.vista() === 'chatbot';
  }

  // Chatbot: el general (null) o el de una tienda.
  protected readonly chatEmpresa = signal<number | null>(null);
  protected readonly chatbots = computed(() => this.modelos().filter((m) => m.tarea === 'chatbot'));
  private readonly empresaModelo = computed(() => (this.vista() === 'chatbot' ? this.chatEmpresa() : null));
  protected readonly modelo = computed(
    () => this.modelos().find((m) => m.tarea === this.vista() && m.empresa_id === this.empresaModelo()) ?? null,
  );
  protected readonly ejemplos = computed(() => {
    const v = this.vista();
    return v === 'reportes' || v === 'chatbot' ? EJEMPLOS[v] : [];
  });
  protected readonly maxMatriz = computed(() => Math.max(1, ...(this.modelo()?.activo.metricas.matriz_confusion.flat() ?? [1])));

  async ngOnInit(): Promise<void> {
    void firstValueFrom(this.http.get<NonNullable<ReturnType<typeof this.lenguaje>>>(`${this.api}/modelo-lenguaje`))
      .then((l) => this.lenguaje.set(l))
      .catch(() => undefined);
    await this.cargar();
    void this.cargarDatos();
    try {
      const es = await this.plataforma.empresas();
      this.empresas.set(es.map((e) => ({ id: e.id, nombre: e.nombre })));
      this.empresaId.set(es[0]?.id ?? null);
    } catch {
      this.empresas.set([]);
    }
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      this.modelos.set(await firstValueFrom(this.http.get<Modelo[]>(this.api)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudieron cargar los modelos.'));
    } finally {
      this.cargando.set(false);
    }
  }

  // ?empresa_id= cuando es el chatbot de una tienda.
  private get params(): Record<string, number> {
    const e = this.empresaModelo();
    return e === null ? {} : { empresa_id: e };
  }

  private async cargarDatos(): Promise<void> {
    if (!this.esClasificador) return;
    this.datos.set(
      await firstValueFrom(
        this.http.get<NonNullable<ReturnType<typeof this.datos>>>(`${this.api}/${this.vista()}/datos`, { params: this.params }),
      ),
    );
  }

  protected elegirChatbot(empresaId: number | null): void {
    this.chatEmpresa.set(empresaId);
    this.prueba.set(null);
    void this.cargarDatos();
  }

  protected cambiarVista(v: Vista): void {
    this.vista.set(v);
    this.prueba.set(null);
    this.error.set('');
    if (v === 'reportes' || v === 'chatbot') {
      this.frase.set(EJEMPLOS[v as Clasificador][0]);
      void this.cargarDatos();
    }
    if (v === 'recomendaciones' && !this.recom()) void this.cargarRecom();
  }

  protected elegirTiendaRecom(id: number): void {
    this.empresaId.set(id);
    void this.cargarRecom();
  }

  private async cargarRecom(): Promise<void> {
    const id = this.empresaId();
    if (id === null) return;
    this.recomCargando.set(true);
    this.recom.set(null);
    this.recomPrueba.set(null);
    this.recomProducto.set(null);
    this.error.set('');
    try {
      this.recom.set(await firstValueFrom(this.http.get<Recomendador>(`${this.api}/recomendaciones/modelo`, { params: { empresa_id: id } })));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo cargar el recomendador.'));
    } finally {
      this.recomCargando.set(false);
    }
  }

  protected async reentrenarRecom(): Promise<void> {
    const id = this.empresaId();
    if (id === null) return;
    this.entrenando.set(true);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${this.api}/recomendaciones/entrenar`, {}, { params: { empresa_id: id } }));
      await this.cargarRecom();
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo reentrenar el recomendador.'));
    } finally {
      this.entrenando.set(false);
    }
  }

  protected async probarRecom(productoId: number): Promise<void> {
    const id = this.empresaId();
    if (id === null) return;
    this.recomProducto.set(productoId);
    try {
      this.recomPrueba.set(
        await firstValueFrom(
          this.http.get<Sugerida[]>(`${this.api}/recomendaciones/probar`, { params: { empresa_id: id, producto_id: productoId } }),
        ),
      );
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo probar el recomendador.'));
    }
  }

  protected async reentrenar(): Promise<void> {
    this.entrenando.set(true);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${this.api}/${this.vista()}/entrenar`, {}, { params: this.params }));
      await this.cargar();
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo reentrenar el modelo.'));
    } finally {
      this.entrenando.set(false);
    }
  }

  protected async probar(texto = this.frase()): Promise<void> {
    if (!texto.trim()) return;
    this.frase.set(texto);
    this.probando.set(true);
    try {
      this.prueba.set(await firstValueFrom(this.http.post<Prueba>(`${this.api}/${this.vista()}/probar`, { texto }, { params: this.params })));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo probar la frase.'));
    } finally {
      this.probando.set(false);
    }
  }

  protected async segmentar(): Promise<void> {
    const id = this.empresaId();
    if (id === null) return;
    this.segmentando.set(true);
    this.error.set('');
    try {
      this.segmentos.set(await firstValueFrom(this.http.get<Segmentos>(`${this.api}/segmentos`, { params: { empresa_id: id } })));
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo segmentar a los clientes.'));
    } finally {
      this.segmentando.set(false);
    }
  }

  protected etiqueta(intencion: string): string {
    return intencion.replace(/_/g, ' ');
  }

  protected opacidad(v: number): number {
    return v === 0 ? 0 : 0.15 + (0.85 * v) / this.maxMatriz();
  }

  protected segmentosLabels(s: Segmentos): string[] {
    return s.segmentos.map((g) => g.segmento);
  }

  protected segmentosData(s: Segmentos): number[] {
    return s.segmentos.map((g) => g.clientes);
  }
}
