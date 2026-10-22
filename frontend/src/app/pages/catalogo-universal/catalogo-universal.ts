import { Component, inject } from '@angular/core';
import { Hero } from '../../components/hero/hero';
import { ProductGrid } from '../../components/product-grid/product-grid';
import { ShopFilters } from '../../components/shop-filters/shop-filters';
import { CatalogoPublico } from '../../services/catalogo-publico';
import { TiendaFiltros } from '../../services/tienda-filtros';

@Component({
  selector: 'app-catalogo-universal',
  imports: [Hero, ShopFilters, ProductGrid],
  templateUrl: './catalogo-universal.html',
  styleUrl: './catalogo-universal.scss',
})
// Catalogo universal (/catalogo): las prendas de todas las boutiques de
// Arlani en un solo lugar. Misma pagina que el catalogo de una boutique
// (portada con video, filtros y grilla), con la marca de la plataforma y un
// filtro mas para elegir la boutique. Cada prenda lleva a su tienda.
export class CatalogoUniversal {
  constructor() {
    inject(CatalogoPublico).tienda.set(null);
    inject(TiendaFiltros).entrarCatalogo(null);
  }
}
