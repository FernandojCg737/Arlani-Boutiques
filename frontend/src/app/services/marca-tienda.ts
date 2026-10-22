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
@Injectable({ providedIn: 'root' })
export class MarcaTienda {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private cargadaPara: number | null = null;

  readonly marca = signal<MarcaEmpresa | null>(null);

  readonly nombre = computed(() => this.marca()?.nombre ?? MARCA_PLATAFORMA.nombre);
  // Sin logo propio, la tienda se muestra con su inicial (ver el panel).
  readonly logo = computed(() => {
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
  readonly inicial = computed(() => this.nombre().trim()[0]?.toUpperCase() ?? 'A');
  // Color para fondos con texto blanco (barra del panel, botones, títulos).
  readonly colorFuerte = computed(() => {
    const m = this.marca();
    return m ? colorParaTextoBlanco(m.color_marca) : null;
  });

  async cargar(): Promise<void> {
    const usuario = this.auth.currentUser();
    if (!usuario || this.cargadaPara === usuario.id) return;
    this.cargadaPara = usuario.id;
    try {
      this.marca.set(await firstValueFrom(this.http.get<MarcaEmpresa>(`${environment.apiUrl}/mi-empresa/marca`)));
    } catch {
      // Sin tienda (SuperAdministrador) o sin conexión: marca de la plataforma.
      this.marca.set(null);
    }
  }
}
