import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { coincidePublico } from '../../data/publicos';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Product } from '../../data/products';
import { CatalogoPublico, isAgotado } from '../../services/catalogo-publico';
import { TiendaFiltros } from '../../services/tienda-filtros';

@Component({
  selector: 'app-product-grid',
  imports: [RouterLink],
  templateUrl: './product-grid.html',
  styleUrl: './product-grid.scss',
})
export class ProductGrid implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly catalogo = inject(CatalogoPublico);
  private readonly filtros = inject(TiendaFiltros);

  protected readonly sortOpen = signal(false);
  protected readonly sortLabel = signal('Predeterminado');

  protected readonly sortOptions = [
    'Predeterminado',
    'Precio: menor a mayor',
    'Precio: mayor a menor',
    'Mas recientes',
  ];

  protected readonly loadingMore = signal(false);
  protected readonly busqueda = signal('');
  protected readonly isAgotado = isAgotado;
  // Catalogo universal: cada prenda dice de que boutique es.
  protected readonly esUniversal = computed(() => !this.catalogo.tienda());

  protected readonly visibleProducts = computed<Product[]>(() => {
    const termino = this.busqueda().trim().toLowerCase();
    const temporada = this.filtros.temporadaSeleccionada();
    const categoria = this.filtros.categoriaSeleccionada();
    const publico = this.filtros.publicoSeleccionado();
    const marcas = this.filtros.marcasSeleccionadas();
    const sucursal = this.filtros.sucursalSeleccionada();
    const precioMin = this.filtros.precioMin();
    const precioMax = this.filtros.precioMax();
    const tienda = this.esUniversal() ? this.filtros.tiendaSeleccionada() : null;

    const productos = this.catalogo.products().filter((p) => {
      const coincideTienda = !tienda || p.tienda === tienda;
      const coincideBusqueda =
        !termino ||
        p.name.toLowerCase().includes(termino) ||
        (p.brand ?? '').toLowerCase().includes(termino) ||
        (this.esUniversal() && (p.tiendaNombre ?? '').toLowerCase().includes(termino));
      const coincideTemporada = !temporada || p.temporada === temporada;
      const coincideCategoria = !categoria || p.category === categoria;
      const paraQuien = coincidePublico(p.publico, publico);
      const coincideMarca = marcas.size === 0 || (p.brand ? marcas.has(p.brand) : false);
      const coincideSucursal = !sucursal || p.branchesInStock.includes(sucursal);
      const coincidePrecioMin = precioMin === null || p.price >= precioMin;
      const coincidePrecioMax = precioMax === null || p.price <= precioMax;
      return (
        coincideTienda &&
        coincideBusqueda &&
        coincideTemporada &&
        coincideCategoria &&
        paraQuien &&
        coincideMarca &&
        coincideSucursal &&
        coincidePrecioMin &&
        coincidePrecioMax
      );
    });

    const ordenado = [...productos];
    switch (this.sortLabel()) {
      case 'Precio: menor a mayor':
        ordenado.sort((a, b) => a.price - b.price);
        break;
      case 'Precio: mayor a menor':
        ordenado.sort((a, b) => b.price - a.price);
        break;
      default:
        break;
    }
    return ordenado;
  });

  ngOnInit(): void {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      this.busqueda.set(params.get('buscar') ?? '');
    });

    this.catalogo.load();
  }

  protected toggleSort(): void {
    this.sortOpen.update((open) => !open);
  }

  protected selectSort(option: string): void {
    this.sortLabel.set(option);
    this.sortOpen.set(false);
  }

  // TODO: reemplazar con la llamada real al backend (paginacion de Producto)
  // cuando el catalogo este conectado. Por ahora solo simula el estado de
  // carga, no hay mas productos de prueba que agregar.
  protected loadMore(): void {
    this.loadingMore.set(true);
    setTimeout(() => this.loadingMore.set(false), 600);
  }

  // El carrito ahora requiere elegir talla y color (backend real, CU11) --
  // en vez de agregar a ciegas una variante desde la grilla, se manda al
  // detalle del producto donde esta el selector real de talla/color.
  protected addToCart(product: Product): void {
    if (isAgotado(product)) return;
    void this.router.navigate(['/producto', product.id]);
  }
}
