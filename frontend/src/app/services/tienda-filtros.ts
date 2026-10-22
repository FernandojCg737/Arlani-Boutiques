import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class TiendaFiltros {
  // Catalogo universal: boutique elegida (subdominio); null = todas.
  readonly tiendaSeleccionada = signal<string | null>(null);
  readonly temporadaSeleccionada = signal<string | null>(null);
  readonly categoriaSeleccionada = signal<string | null>(null);
  readonly marcasSeleccionadas = signal<Set<string>>(new Set());
  readonly sucursalSeleccionada = signal<string | null>(null);
  readonly precioMin = signal<number | null>(null);
  readonly precioMax = signal<number | null>(null);

  // Catalogo que se esta viendo (subdominio; null = el universal). Al pasar a
  // otro los filtros se limpian (sus sucursales y temporadas son otras); al
  // volver del detalle de un producto al mismo catalogo se mantienen.
  private catalogoActual: string | null | undefined = undefined;

  entrarCatalogo(tienda: string | null): void {
    if (tienda !== this.catalogoActual) this.limpiarTodo();
    this.catalogoActual = tienda;
  }

  // Al cambiar de boutique, sus sucursales, temporadas y marcas son otras.
  seleccionarTienda(subdominio: string | null): void {
    this.tiendaSeleccionada.set(subdominio);
    this.sucursalSeleccionada.set(null);
    this.temporadaSeleccionada.set(null);
    this.marcasSeleccionadas.set(new Set());
  }

  seleccionarTemporada(nombre: string | null): void {
    this.temporadaSeleccionada.set(nombre);
  }

  seleccionarCategoria(id: string | null): void {
    this.categoriaSeleccionada.set(id);
  }

  toggleMarca(nombre: string): void {
    this.marcasSeleccionadas.update((set) => {
      const next = new Set(set);
      next.has(nombre) ? next.delete(nombre) : next.add(nombre);
      return next;
    });
  }

  limpiarMarcas(): void {
    this.marcasSeleccionadas.set(new Set());
  }

  seleccionarSucursal(nombre: string | null): void {
    this.sucursalSeleccionada.set(nombre);
  }

  setPrecio(min: number | null, max: number | null): void {
    this.precioMin.set(min);
    this.precioMax.set(max);
  }

  limpiarTodo(): void {
    this.tiendaSeleccionada.set(null);
    this.temporadaSeleccionada.set(null);
    this.categoriaSeleccionada.set(null);
    this.marcasSeleccionadas.set(new Set());
    this.sucursalSeleccionada.set(null);
    this.precioMin.set(null);
    this.precioMax.set(null);
  }
}
