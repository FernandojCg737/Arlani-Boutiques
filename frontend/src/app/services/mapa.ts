import { Injectable } from '@angular/core';

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    L?: any;
  }
}

const LEAFLET = 'https://unpkg.com/leaflet@1.9.4/dist';

// Santa Cruz de la Sierra: centro del mapa si el cliente no comparte su ubicacion.
export const CENTRO_POR_DEFECTO = { lat: -17.7833, lng: -63.1821 };

export interface Punto {
  lat: number;
  lng: number;
}

// Mapa de OpenStreetMap con Leaflet (sin clave ni cuenta). Se carga una vez
// desde el CDN, igual que el SDK de PayPal.
@Injectable({ providedIn: 'root' })
export class Mapa {
  private promesa: Promise<unknown> | null = null;

  cargar(): Promise<unknown> {
    if (window.L) return Promise.resolve(window.L);
    if (this.promesa) return this.promesa;
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = `${LEAFLET}/leaflet.css`;
    document.head.appendChild(css);
    this.promesa = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = `${LEAFLET}/leaflet.js`;
      script.onload = () => resolve(window.L);
      script.onerror = () => {
        this.promesa = null;
        reject(new Error('No se pudo cargar el mapa.'));
      };
      document.head.appendChild(script);
    });
    return this.promesa;
  }

  // Ubicacion actual del dispositivo (GPS del navegador o del celular).
  ubicacionActual(): Promise<Punto> {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('Tu navegador no permite compartir la ubicación.'));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
        (e) =>
          reject(
            new Error(
              e.code === e.PERMISSION_DENIED
                ? 'No diste permiso para usar tu ubicación. Mueve el pin en el mapa.'
                : 'No pudimos obtener tu ubicación. Mueve el pin en el mapa.',
            ),
          ),
        { enableHighAccuracy: true, timeout: 12000 },
      );
    });
  }

  // Calle aproximada de un punto (OpenStreetMap Nominatim), para sugerir el texto.
  async direccionDe(p: Punto): Promise<{ direccion: string; ciudad: string | null } | null> {
    try {
      const r = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&accept-language=es&lat=${p.lat}&lon=${p.lng}`,
      );
      if (!r.ok) return null;
      const d = await r.json();
      const a = d.address ?? {};
      const calle = [a.road, a.house_number].filter(Boolean).join(' ');
      const zona = a.suburb ?? a.neighbourhood ?? a.quarter ?? '';
      return {
        direccion: [calle, zona].filter(Boolean).join(', ') || d.display_name || '',
        ciudad: a.city ?? a.town ?? a.village ?? null,
      };
    } catch {
      return null;
    }
  }
}

export function enlaceMapa(lat: number | string, lng: number | string): string {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}`;
}
