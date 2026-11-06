import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LiveSala } from '../../../components/live-sala/live-sala';
import { Auth } from '../../../services/auth';
import { ComentarioRepeticion, LiveApi, LiveResumen, fechaUtc } from '../../../services/live';
import { EmpresaTenant, PlataformaApi, mensajeError } from '../../../services/plataforma';

interface ProductoTienda {
  id: number;
  nombre: string;
  precio: number;
  imagen: string | null;
  stock: number;
}

// CU22 Gestionar live commerce. La tienda (plan Profesional) inicia su live,
// transmite y modera desde aquí, y ve o borra sus grabaciones. El
// SuperAdministrador ve los lives en curso de todas las tiendas, puede cortarlos
// y ve o borra las grabaciones de cualquiera.
@Component({
  selector: 'app-admin-live',
  imports: [DatePipe, DecimalPipe, RouterLink, LiveSala],
  templateUrl: './live.html',
  styleUrls: ['../ventas/ventas.scss', '../backups/backups.scss', './live.scss'],
})
export class AdminLive implements OnInit, OnDestroy {
  private readonly api = inject(LiveApi);
  private readonly auth = inject(Auth);
  private readonly plataforma = inject(PlataformaApi);
  private sondeo: ReturnType<typeof setInterval> | null = null;

  protected readonly fechaUtc = fechaUtc;
  protected readonly esSuper = this.auth.isSuperAdmin();
  protected readonly cargando = signal(true);
  protected readonly error = signal('');

  // Tienda
  protected readonly disponible = signal(false);
  protected readonly configurado = signal(true);
  protected readonly plan = signal<string | null>(null);
  protected readonly actual = signal<LiveResumen | null>(null);
  protected readonly productos = signal<ProductoTienda[]>([]);
  protected readonly elegidos = signal<number[]>([]);
  protected readonly titulo = signal('');
  protected readonly descripcion = signal('');
  protected readonly buscar = signal('');
  protected readonly iniciando = signal(false);

  // SuperAdministrador
  protected readonly enVivo = signal<LiveResumen[]>([]);
  protected readonly tiendas = signal<EmpresaTenant[]>([]);
  protected readonly tiendaFiltro = signal<number | null>(null);
  protected readonly cortando = signal<LiveResumen | null>(null);
  protected readonly motivo = signal('');

  // Historial y grabaciones
  protected readonly historial = signal<LiveResumen[]>([]);
  protected readonly video = signal<{ live: LiveResumen; url: string } | null>(null);
  // Repetición con chat: los comentarios del live y el segundo que se está viendo.
  protected readonly repeticion = signal<ComentarioRepeticion[]>([]);
  protected readonly segundo = signal(0);
  protected readonly comentarioActual = computed(() => {
    let id: number | null = null;
    for (const c of this.repeticion()) {
      if (c.segundo > this.segundo()) break;
      id = c.id;
    }
    return id;
  });
  private ultimoActual: number | null = null;

  protected readonly productosFiltrados = computed(() => {
    const q = this.buscar().trim().toLowerCase();
    return q ? this.productos().filter((p) => p.nombre.toLowerCase().includes(q)) : this.productos();
  });

  async ngOnInit(): Promise<void> {
    if (this.esSuper) this.plataforma.empresas().then((t) => this.tiendas.set(t), () => undefined);
    await this.cargar();
    // Grabaciones que se están procesando y lives en curso: se refrescan solos.
    this.sondeo = setInterval(() => {
      const procesando = this.historial().some((l) => l.grabacion_estado === 'procesando' || l.grabacion_estado === 'grabando');
      if (this.esSuper || procesando) void this.cargar(false);
    }, 15000);
  }

  ngOnDestroy(): void {
    if (this.sondeo) clearInterval(this.sondeo);
  }

  protected async cargar(conIndicador = true): Promise<void> {
    if (conIndicador) this.cargando.set(true);
    this.error.set('');
    try {
      if (this.esSuper) {
        const [vivos, historial] = await Promise.all([this.api.revisarEnVivo(), this.api.historial(this.tiendaFiltro())]);
        this.enVivo.set(vivos);
        this.historial.set(historial.filter((l) => l.estado !== 'en_vivo'));
      } else {
        const [estado, historial] = await Promise.all([this.api.estadoTienda(), this.api.historial()]);
        this.disponible.set(estado.disponible);
        this.configurado.set(estado.configurado);
        this.plan.set(estado.plan);
        this.actual.set(estado.actual);
        this.historial.set(historial.filter((l) => l.estado !== 'en_vivo'));
        if (estado.disponible && !estado.actual && !this.productos().length) {
          this.productos.set(await this.api.productosTienda());
        }
      }
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar los lives.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected alternar(id: number): void {
    this.elegidos.update((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  protected async iniciar(): Promise<void> {
    if (this.titulo().trim().length < 3) {
      this.error.set('Ponle un título a tu live (por ejemplo: "Nueva colección de verano").');
      return;
    }
    this.iniciando.set(true);
    this.error.set('');
    try {
      const sala = await this.api.iniciar(this.titulo().trim(), this.descripcion().trim(), this.elegidos());
      this.actual.set(sala.live);
      this.titulo.set('');
      this.descripcion.set('');
      this.elegidos.set([]);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo iniciar el live.'));
    } finally {
      this.iniciando.set(false);
    }
  }

  protected terminado(): void {
    setTimeout(() => void this.cargar(), 2500);
  }

  protected duracion(l: LiveResumen): string {
    const segundos = l.grabacion_segundos ?? (l.fin ? (Date.parse(fechaUtc(l.fin)!) - Date.parse(fechaUtc(l.inicio)!)) / 1000 : 0);
    const m = Math.round(segundos / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }

  protected estadoGrabacion(l: LiveResumen): string {
    return {
      pendiente: 'Sin grabación',
      grabando: 'Grabando…',
      procesando: 'Procesando…',
      lista: 'Lista',
      fallida: 'No se pudo grabar',
      borrada: 'Borrada',
    }[l.grabacion_estado];
  }

  protected async verGrabacion(l: LiveResumen): Promise<void> {
    try {
      const [{ url }, comentarios] = await Promise.all([this.api.grabacion(l.id), this.api.comentariosDelLive(l.id)]);
      this.repeticion.set(comentarios);
      this.segundo.set(0);
      this.ultimoActual = null;
      this.video.set({ live: l, url });
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo abrir la grabación.'));
    }
  }

  // El chat acompaña al video: se resalta y se muestra el comentario de ese momento.
  protected alAvanzar(tiempo: number): void {
    this.segundo.set(tiempo);
    const actual = this.comentarioActual();
    if (actual !== null && actual !== this.ultimoActual) {
      this.ultimoActual = actual;
      document.getElementById(`rc-${actual}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  protected irA(video: HTMLVideoElement, c: ComentarioRepeticion): void {
    video.currentTime = c.segundo;
    void video.play();
  }

  protected minuto(segundos: number): string {
    const h = Math.floor(segundos / 3600);
    const m = Math.floor((segundos % 3600) / 60);
    const s = segundos % 60;
    const mmss = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return h ? `${h}:${mmss}` : mmss;
  }

  protected descargarComentarios(l: LiveResumen): void {
    const celda = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const filas = [
      ['Minuto del video', 'Hora', 'Usuario', 'Comentario', 'Estado'],
      ...this.repeticion().map((c) => [
        this.minuto(c.segundo),
        new Date(fechaUtc(c.fecha)!).toLocaleString('es-BO'),
        c.usuario + (c.es_tienda ? ' (tienda)' : ''),
        c.texto,
        c.oculto ? 'Oculto' : 'Visible',
      ]),
    ];
    // Con BOM para que Excel lea bien las tildes y los emojis.
    const csv = '\ufeff' + filas.map((f) => f.map(celda).join(';')).join('\r\n');
    const enlace = document.createElement('a');
    enlace.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    enlace.download = `comentarios-live-${l.id}.csv`;
    enlace.click();
    URL.revokeObjectURL(enlace.href);
  }

  protected async borrarGrabacion(l: LiveResumen): Promise<void> {
    if (!confirm(`¿Borrar la grabación de «${l.titulo}»? No se puede recuperar.`)) return;
    try {
      await this.api.borrarGrabacion(l.id);
      await this.cargar(false);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo borrar la grabación.'));
    }
  }

  protected filtrarTienda(valor: string): void {
    this.tiendaFiltro.set(valor ? Number(valor) : null);
    void this.cargar();
  }

  protected abrirCorte(l: LiveResumen): void {
    this.motivo.set('');
    this.cortando.set(l);
  }

  protected async cortar(): Promise<void> {
    const l = this.cortando();
    if (!l) return;
    if (this.motivo().trim().length < 5) {
      this.error.set('Escribe el motivo del corte (la tienda lo recibe).');
      return;
    }
    try {
      await this.api.cortar(l.id, this.motivo().trim());
      this.cortando.set(null);
      await this.cargar(false);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo cortar el live.'));
    }
  }
}
