import { Component, computed, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { Hero } from '../../components/hero/hero';
import { ProductGrid } from '../../components/product-grid/product-grid';
import { ShopFilters } from '../../components/shop-filters/shop-filters';
import { SucursalPublica } from '../../services/tienda-publica';
import { TiendaActiva } from '../../services/tienda-activa';
import { TiendaFiltros } from '../../services/tienda-filtros';

@Component({
  selector: 'app-tienda',
  imports: [Hero, ShopFilters, ProductGrid],
  templateUrl: './tienda.html',
  styleUrl: './tienda.scss',
})
// Pagina de una boutique (/tienda-<subdominio>): su encabezado, portada con
// video, catalogo (solo sus productos y filtros), sucursales y pie, todo con
// su logo y su color. Sin productos todavia, avisa que lo esta preparando.
export class Tienda {
  protected readonly tienda = inject(TiendaActiva);

  protected readonly antetitulo = computed(() => (this.tienda.esOriginal() ? '' : 'Catálogo'));
  protected readonly titulo = computed(() =>
    this.tienda.esOriginal() ? 'CATALOGO' : this.tienda.nombre().toUpperCase(),
  );
  protected readonly subtitulo = computed(() => {
    if (this.tienda.esOriginal())
      return 'Explora la coleccion completa. Todos nuestros productos disponibles en un solo lugar.';
    const ciudad = this.tienda.tienda()?.ciudad;
    return `Prendas elegidas para ti${ciudad ? ' desde ' + ciudad : ''}. Compra en línea o reserva y retira en nuestras sucursales.`;
  });
  // Mientras carga se asume que tiene productos (asi no parpadea el aviso).
  protected readonly sinProductos = computed(() => this.tienda.tienda()?.tiene_catalogo === false);
  protected readonly sucursales = computed<SucursalPublica[]>(() =>
    this.tienda.esOriginal() ? [] : (this.tienda.tienda()?.sucursales ?? []),
  );

  constructor() {
    const subdominio = inject(ActivatedRoute).snapshot.paramMap.get('subdominio');
    inject(TiendaFiltros).entrarCatalogo(subdominio);
    this.tienda.activar(subdominio);
  }

  protected mapa(s: SucursalPublica): string {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.direccion}, ${s.ciudad}`)}`;
  }
}
