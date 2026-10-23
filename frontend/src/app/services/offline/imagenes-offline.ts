import { Injectable, inject, signal } from '@angular/core';
import { OfflineDb } from './offline-db';

const EN_PARALELO = 6;

// Fotos de las prendas para el modo sin conexión: al descargar el paquete se
// bajan también las imágenes y se guardan en IndexedDB; las pantallas las
// muestran desde el dispositivo (URL local), con o sin internet.
@Injectable({ providedIn: 'root' })
export class ImagenesOffline {
  private readonly db = inject(OfflineDb);
  private readonly locales = signal<Record<string, string>>({});

  // La imagen guardada en el dispositivo; si no está, la de internet (solo con conexión).
  src(url: string | null, enLinea: boolean): string | null {
    if (!url) return null;
    return this.locales()[url] ?? (enLinea ? url : null);
  }

  // Descarga y guarda las que falten (las que no se pueden bajar se omiten).
  async descargar(urls: (string | null)[]): Promise<number> {
    const pendientes = [...new Set(urls.filter((u): u is string => !!u))];
    let guardadas = 0;
    const trabajar = async () => {
      for (let u = pendientes.shift(); u; u = pendientes.shift()) {
        try {
          if (await this.db.imagen(u)) {
            guardadas++;
            continue;
          }
          const r = await fetch(u, { mode: 'cors' });
          if (!r.ok) continue;
          await this.db.guardarImagen(u, await r.blob());
          guardadas++;
        } catch {
          // Sin CORS o sin red: esa foto se verá solo con conexión.
        }
      }
    };
    await Promise.all(Array.from({ length: EN_PARALELO }, trabajar));
    return guardadas;
  }

  // Prepara las URL locales de las fotos guardadas.
  async cargar(urls: (string | null)[]): Promise<void> {
    const actuales = { ...this.locales() };
    for (const u of new Set(urls.filter((x): x is string => !!x))) {
      if (actuales[u]) continue;
      const blob = await this.db.imagen(u);
      if (blob) actuales[u] = URL.createObjectURL(blob);
    }
    this.locales.set(actuales);
  }
}
