import {
  Component,
  ElementRef,
  OnDestroy,
  afterNextRender,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { CENTRO_POR_DEFECTO, Mapa, Punto } from '../../services/mapa';

// Mapa con un pin: el cliente usa su ubicacion actual (GPS) o mueve el pin.
// En solo lectura muestra un punto (ej. la direccion de envio de una venta).
@Component({
  selector: 'app-mapa-ubicacion',
  template: `
    <div class="mapa" #contenedor [style.height.px]="alto()"></div>
    @if (!soloLectura()) {
      <div class="mapa__barra">
        <button type="button" (click)="usarMiUbicacion()" [disabled]="buscando()">
          {{ buscando() ? 'Buscando tu ubicación…' : '📍 Usar mi ubicación actual' }}
        </button>
        <span>o toca el mapa / arrastra el pin hasta tu puerta</span>
      </div>
      @if (error()) {
        <p class="mapa__error" role="alert">{{ error() }}</p>
      }
    }
  `,
  styles: `
    :host { display: block; }
    .mapa { width: 100%; border: 1px solid #ddd; background: #eef1f4; }
    .mapa__barra { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin-top: 8px; font-size: 12px; color: #777; }
    .mapa__barra button {
      border: 1px solid var(--brand-dark, #1f2a44); background: #fff; color: var(--brand-dark, #1f2a44);
      padding: 7px 12px; font: inherit; font-size: 12px; font-weight: 700; cursor: pointer;
    }
    .mapa__barra button:disabled { opacity: 0.6; cursor: default; }
    .mapa__error { margin: 6px 0 0; font-size: 12px; color: #b3261e; }
  `,
})
export class MapaUbicacion implements OnDestroy {
  private readonly mapa = inject(Mapa);

  readonly punto = input<Punto | null>(null);
  readonly soloLectura = input(false);
  readonly alto = input(260);
  readonly cambio = output<Punto>();

  protected readonly buscando = signal(false);
  protected readonly error = signal('');
  private readonly contenedor = viewChild.required<ElementRef<HTMLDivElement>>('contenedor');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private leaflet: any = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private pin: any = null;

  constructor() {
    afterNextRender(() => void this.iniciar());
    // Si cambia el punto desde afuera (otra direccion), se mueve el pin.
    effect(() => {
      const p = this.punto();
      if (p && this.pin) this.ubicar(p, false);
    });
  }

  private async iniciar(): Promise<void> {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const L = (await this.mapa.cargar()) as any;
      const inicio = this.punto() ?? CENTRO_POR_DEFECTO;
      this.leaflet = L.map(this.contenedor().nativeElement, { scrollWheelZoom: !this.soloLectura() }).setView(
        [inicio.lat, inicio.lng],
        this.punto() ? 17 : 13,
      );
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap',
      }).addTo(this.leaflet);
      const icono = L.icon({
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
      });
      this.pin = L.marker([inicio.lat, inicio.lng], { draggable: !this.soloLectura(), icon: icono }).addTo(this.leaflet);
      if (!this.soloLectura()) {
        this.pin.on('dragend', () => {
          const { lat, lng } = this.pin.getLatLng();
          this.cambio.emit({ lat, lng });
        });
        this.leaflet.on('click', (e: { latlng: Punto }) => this.ubicar(e.latlng, true));
        // Sin punto guardado: se intenta arrancar en la ubicacion del cliente.
        if (!this.punto()) void this.usarMiUbicacion();
      }
      setTimeout(() => this.leaflet?.invalidateSize(), 150);
    } catch {
      this.error.set('No se pudo cargar el mapa. Revisa tu conexión.');
    }
  }

  private ubicar(p: Punto, avisar: boolean): void {
    const actual = this.pin?.getLatLng();
    if (!avisar && actual && Math.abs(actual.lat - p.lat) < 1e-7 && Math.abs(actual.lng - p.lng) < 1e-7) return;
    this.pin?.setLatLng([p.lat, p.lng]);
    this.leaflet?.setView([p.lat, p.lng], Math.max(this.leaflet.getZoom(), 16));
    if (avisar) this.cambio.emit({ lat: p.lat, lng: p.lng });
  }

  protected async usarMiUbicacion(): Promise<void> {
    this.buscando.set(true);
    this.error.set('');
    try {
      this.ubicar(await this.mapa.ubicacionActual(), true);
    } catch (e) {
      this.error.set((e as Error).message);
    } finally {
      this.buscando.set(false);
    }
  }

  ngOnDestroy(): void {
    this.leaflet?.remove();
  }
}
