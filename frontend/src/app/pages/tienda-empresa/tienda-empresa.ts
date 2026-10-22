import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ProductGrid } from '../../components/product-grid/product-grid';
import { ShopFilters } from '../../components/shop-filters/shop-filters';
import { CatalogoPublico } from '../../services/catalogo-publico';
import { colorParaTextoBlanco, esLogoOscuro } from '../../services/marca-tienda';
import { SucursalPublica, TiendaPublica, TiendaPublicaApi } from '../../services/tienda-publica';

// Pagina publica de una tienda en /tienda-<subdominio>: su marca, su catalogo
// (solo sus productos) y sus sucursales. La tienda original tiene su sitio
// completo en esa misma direccion (ver app.routes.ts).
@Component({
  selector: 'app-tienda-empresa',
  imports: [RouterLink, ShopFilters, ProductGrid],
  templateUrl: './tienda-empresa.html',
  styleUrl: './tienda-empresa.scss',
})
export class TiendaEmpresa {
  private readonly api = inject(TiendaPublicaApi);
  private readonly catalogo = inject(CatalogoPublico);
  private readonly subdominio = inject(ActivatedRoute).snapshot.paramMap.get('subdominio') ?? '';

  protected readonly tienda = signal<TiendaPublica | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noExiste = signal(false);
  protected readonly error = signal(false);
  // Logo oscuro sobre la portada (siempre oscura): con contorno claro.
  protected readonly logoOscuro = signal(false);

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const tienda = await this.api.obtener(this.subdominio);
      if (tienda) {
        this.catalogo.tienda.set(tienda.subdominio);
        this.tienda.set(tienda);
        void esLogoOscuro(tienda.logo_url).then((oscuro) => this.logoOscuro.set(oscuro));
      } else this.noExiste.set(true);
    } catch {
      this.error.set(true);
    } finally {
      this.cargando.set(false);
    }
  }

  // Fondo de la portada: el color de la tienda, oscurecido si el titulo blanco no se leeria.
  protected colorPortada(hex: string): string {
    return colorParaTextoBlanco(hex);
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  protected mapa(s: SucursalPublica): string {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.direccion}, ${s.ciudad}`)}`;
  }
}
