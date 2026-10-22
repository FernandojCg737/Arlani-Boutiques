import { HttpClient } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { Auth } from './auth';

export interface MarcaEmpresa {
  nombre: string;
  subdominio: string;
  ciudad: string | null;
  color_marca: string;
  logo_url: string | null;
  email_contacto: string | null;
}

// Sin tienda (SuperAdministrador): la marca de la plataforma.
const MARCA_PLATAFORMA = { nombre: 'Arlani Boutiques', logo: '/img/arlani-logo-claro.png' };
// Barra del panel mientras llega la marca: gris neutro, de ninguna tienda.
const COLOR_CARGANDO = '#2b2b2b';

// Texto blanco legible: el color tiene que tener contraste >= 4.5 con el
// blanco (WCAG AA). Un color de marca claro se oscurece lo justo.
function luminancia([r, g, b]: number[]): number {
  const canal = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b);
}

export function colorParaTextoBlanco(hex: string): string {
  let rgb = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  if (rgb.some(Number.isNaN)) return hex;
  for (let i = 0; i < 20 && 1.05 / (luminancia(rgb) + 0.05) < 4.5; i++) {
    rgb = rgb.map((c) => Math.round(c * 0.88));
  }
  return '#' + rgb.map((c) => c.toString(16).padStart(2, '0')).join('');
}

// ¿El logo es oscuro? (promedio de luminancia de sus pixeles visibles). Sobre
// un fondo oscuro se le pone un contorno claro (.logo-contorno). Se calcula
// una vez por URL.
const logosOscuros = new Map<string, Promise<boolean>>();

export function esLogoOscuro(url: string | null | undefined): Promise<boolean> {
  if (!url) return Promise.resolve(false);
  let pendiente = logosOscuros.get(url);
  if (!pendiente) {
    pendiente = new Promise<boolean>((resolver) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        try {
          const lado = 48;
          const lienzo = document.createElement('canvas');
          lienzo.width = lado;
          lienzo.height = lado;
          const ctx = lienzo.getContext('2d', { willReadFrequently: true });
          if (!ctx) return resolver(false);
          ctx.drawImage(img, 0, 0, lado, lado);
          const datos = ctx.getImageData(0, 0, lado, lado).data;
          let suma = 0;
          let visibles = 0;
          for (let i = 0; i < datos.length; i += 4) {
            if (datos[i + 3] < 128) continue;
            suma += luminancia([datos[i], datos[i + 1], datos[i + 2]]);
            visibles++;
          }
          resolver(visibles > 0 && suma / visibles < 0.3);
        } catch {
          resolver(false);
        }
      };
      img.onerror = () => resolver(false);
      img.src = url;
    });
    logosOscuros.set(url, pendiente);
  }
  return pendiente;
}

// Marca de la tienda del usuario (logo, nombre, color): el panel, los
// reportes y los comprobantes se ven con la identidad de cada boutique.
// La marca se recuerda en el navegador (por usuario): al volver a entrar al
// panel se pinta al instante y después se actualiza con la del servidor.
const CLAVE_MARCA = 'arlani_marca_panel';

@Injectable({ providedIn: 'root' })
export class MarcaTienda {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private cargadaPara: number | null = null;
  private pendiente: Promise<void> | null = null;

  readonly marca = signal<MarcaEmpresa | null>(null);
  // Todavía no se sabe la marca (ni recordada ni del servidor): el panel
  // queda neutro en vez de mostrar el verde de Atelier o el logo de Arlani.
  readonly cargando = signal(true);

  readonly nombre = computed(() => (this.cargando() ? '' : (this.marca()?.nombre ?? MARCA_PLATAFORMA.nombre)));
  // Sin logo propio, la tienda se muestra con su inicial (ver el panel).
  readonly logo = computed(() => {
    if (this.cargando()) return null;
    const m = this.marca();
    return m ? m.logo_url : MARCA_PLATAFORMA.logo;
  });
  // Logo subido por la tienda (los propios del sitio, /img/..., ya estan
  // hechos para el fondo oscuro del panel).
  readonly logoSubido = computed(() => this.logo()?.startsWith('http') ?? false);
  // Logo oscuro: lleva contorno claro sobre la barra del panel (siempre oscura).
  readonly logoOscuro = signal(false);

  constructor() {
    effect(() => {
      const url = this.logoSubido() ? this.logo() : null;
      this.logoOscuro.set(false);
      void esLogoOscuro(url).then((oscuro) => {
        if (this.logo() === url) this.logoOscuro.set(oscuro);
      });
    });
  }
  readonly inicial = computed(() => this.nombre().trim()[0]?.toUpperCase() ?? '');
  // Color para fondos con texto blanco (barra del panel, botones, títulos).
  readonly colorFuerte = computed(() => {
    if (this.cargando()) return COLOR_CARGANDO;
    const m = this.marca();
    return m ? colorParaTextoBlanco(m.color_marca) : null;
  });

  cargar(): Promise<void> {
    const usuario = this.auth.currentUser();
    if (!usuario) return Promise.resolve();
    if (this.cargadaPara === usuario.id && this.pendiente) return this.pendiente;
    this.cargadaPara = usuario.id;

    const recordada = this.leer(usuario.id);
    if (recordada !== undefined) {
      this.marca.set(recordada);
      this.cargando.set(false);
    } else {
      this.cargando.set(true);
    }
    this.pendiente = firstValueFrom(this.http.get<MarcaEmpresa>(`${environment.apiUrl}/mi-empresa/marca`))
      .then((m) => m, () => null) // Sin tienda (SuperAdministrador) o sin conexión: la de la plataforma.
      .then((m) => {
        if (this.cargadaPara !== usuario.id) return;
        this.marca.set(m);
        this.cargando.set(false);
        this.guardar(usuario.id, m);
      });
    return this.pendiente;
  }

  // undefined = no hay nada recordado para este usuario.
  private leer(usuarioId: number): MarcaEmpresa | null | undefined {
    try {
      const guardada = JSON.parse(localStorage.getItem(CLAVE_MARCA) ?? 'null');
      return guardada?.usuario === usuarioId ? guardada.marca : undefined;
    } catch {
      return undefined;
    }
  }

  private guardar(usuarioId: number, marca: MarcaEmpresa | null): void {
    try {
      localStorage.setItem(CLAVE_MARCA, JSON.stringify({ usuario: usuarioId, marca }));
    } catch {
      // Sin localStorage, la marca igual llega del servidor.
    }
  }
}
