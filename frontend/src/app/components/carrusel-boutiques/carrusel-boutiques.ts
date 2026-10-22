import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { BOUTIQUES } from '../../data/boutiques';
import { esLogoOscuro } from '../../services/marca-tienda';
import { rutaTienda } from '../../services/plataforma';
import { TiendaPublicaApi } from '../../services/tienda-publica';

// Cuántos logos tiene que tener cada mitad de la cinta para que llene el
// ancho de la pantalla aunque haya pocas boutiques.
const MINIMO_POR_VUELTA = 8;

interface TiendaEnCinta {
  nombre: string;
  ruta: string;
  // Sin logo se muestra su inicial y su nombre con el color de la marca.
  logo: string | null;
  color: string;
  // Logo oscuro: lleva contorno claro sobre la cinta oscura.
  oscuro?: boolean;
}

interface LogoEnCinta {
  tienda: TiendaEnCinta;
  // Solo la primera aparición de cada boutique es navegable con teclado y
  // lector de pantalla; las repeticiones son decorativas.
  repetido: boolean;
}

// Cinta de logos de las boutiques que venden con Arlani, girando sin fin
// (como la fila de marcas de Shopify). Cada logo lleva al catálogo de su
// boutique. Se pausa con el cursor encima para poder hacer clic tranquilo.
// Las tiendas salen de la base (GET /tiendas: las empresas activas), así cada
// tienda nueva aparece sola; si el servidor no responde, queda la lista fija.
@Component({
  selector: 'app-carrusel-boutiques',
  imports: [RouterLink],
  templateUrl: './carrusel-boutiques.html',
  styleUrl: './carrusel-boutiques.scss',
})
export class CarruselBoutiques {
  private readonly api = inject(TiendaPublicaApi);

  protected readonly logos = signal<LogoEnCinta[]>(
    this.armarCinta(BOUTIQUES.map((b) => ({ nombre: b.nombre, ruta: b.ruta, logo: b.logo, color: '#1f2a44' }))),
  );

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const tiendas = await this.api.listar();
      const lista: TiendaEnCinta[] = await Promise.all(
        tiendas.map(async (t) => ({
          nombre: t.nombre,
          ruta: rutaTienda(t.subdominio),
          logo: t.logo_url,
          color: t.color_marca,
          oscuro: t.logo_url?.startsWith('http') ? await esLogoOscuro(t.logo_url) : false,
        })),
      );
      this.logos.set(this.armarCinta(lista));
    } catch {
      // sin servidor queda la lista fija
    }
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  // La cinta son dos mitades iguales: la animación corre una mitad y vuelve
  // al inicio sin que se note el salto.
  private armarCinta(tiendas: TiendaEnCinta[]): LogoEnCinta[] {
    if (tiendas.length === 0) return [];
    const vuelta: TiendaEnCinta[] = [];
    while (vuelta.length < MINIMO_POR_VUELTA) vuelta.push(...tiendas);
    return [...vuelta, ...vuelta].map((tienda, i) => ({ tienda, repetido: i >= tiendas.length }));
  }
}
