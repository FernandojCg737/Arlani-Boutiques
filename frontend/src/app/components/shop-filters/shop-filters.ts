import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Component, DestroyRef, OnInit, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CatalogoPublico } from '../../services/catalogo-publico';
import { TiendaFiltros } from '../../services/tienda-filtros';

interface Sucursal {
  id: number;
  nombre: string;
  direccion: string;
}

interface TiendaOpcion {
  subdominio: string;
  nombre: string;
  logo: string | null;
  color: string;
}

interface Temporada {
  id: number;
  nombre: string;
}

const PRECIO_MIN = 0;
const PRECIO_MAX = 3500;

@Component({
  selector: 'app-shop-filters',
  imports: [],
  templateUrl: './shop-filters.html',
  styleUrl: './shop-filters.scss',
})
export class ShopFilters implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly filtros = inject(TiendaFiltros);
  private readonly catalogo = inject(CatalogoPublico);

  protected readonly temporadas = signal<Temporada[]>([]);
  protected readonly temporadaSeleccionada = this.filtros.temporadaSeleccionada;

  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly sucursalSeleccionada = this.filtros.sucursalSeleccionada;

  protected readonly categorias = this.catalogo.categorias;
  protected readonly categoriaSeleccionada = this.filtros.categoriaSeleccionada;

  // Catalogo universal (sin boutique fija): se puede elegir la boutique.
  protected readonly esUniversal = computed(() => !this.catalogo.tienda());
  protected readonly tiendaSeleccionada = this.filtros.tiendaSeleccionada;
  protected readonly tiendas = computed<TiendaOpcion[]>(() => {
    const vistas = new Map<string, TiendaOpcion>();
    for (const p of this.catalogo.products()) {
      if (p.tienda && !vistas.has(p.tienda)) {
        vistas.set(p.tienda, {
          subdominio: p.tienda,
          nombre: p.tiendaNombre ?? p.tienda,
          logo: p.tiendaLogo ?? null,
          color: p.tiendaColor ?? '#121a2c',
        });
      }
    }
    return Array.from(vistas.values()).sort((a, b) => a.nombre.localeCompare(b.nombre));
  });

  protected readonly marcasVisibles = computed(() => {
    const categoria = this.categoriaSeleccionada();
    const tienda = this.esUniversal() ? this.tiendaSeleccionada() : null;
    if (!categoria && !tienda) return this.catalogo.marcas();

    const marcasVistas = new Set(
      this.catalogo
        .products()
        .filter((p) => (!categoria || p.category === categoria) && (!tienda || p.tienda === tienda))
        .map((p) => p.brand)
        .filter((b): b is string => !!b),
    );
    return this.catalogo.marcas().filter((m) => marcasVistas.has(m));
  });
  protected readonly marcasSeleccionadas = this.filtros.marcasSeleccionadas;
  protected readonly todasMarcasChecked = computed(() => this.marcasSeleccionadas().size === 0);

  protected readonly precioMin = PRECIO_MIN;
  protected readonly precioMax = PRECIO_MAX;
  protected readonly selectedPrecioMin = signal(PRECIO_MIN);
  protected readonly selectedPrecioMax = signal(PRECIO_MAX);

  protected readonly categoriasOpen = signal(true);
  protected readonly precioOpen = signal(true);

  protected readonly minPercent = computed(
    () => ((this.selectedPrecioMin() - PRECIO_MIN) / (PRECIO_MAX - PRECIO_MIN)) * 100,
  );
  protected readonly maxPercent = computed(
    () => ((this.selectedPrecioMax() - PRECIO_MIN) / (PRECIO_MAX - PRECIO_MIN)) * 100,
  );

  ngOnInit(): void {
    // Permite llegar desde el header con una categoria ya aplicada, ej.
    // /tienda?categoria=poleras.
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const categoria = params.get('categoria');
      if (categoria) this.selectCategoria(categoria);
    });

    this.catalogo.load();

  }

  // Temporadas y sucursales de la tienda que se está viendo (en el catálogo
  // universal, las de la boutique elegida o las de todas).
  private readonly cargarOpciones = effect(() => {
    const tienda = this.catalogo.tienda() ?? this.tiendaSeleccionada();
    const params: Record<string, string> = tienda ? { tienda } : {};
    firstValueFrom(this.http.get<Temporada[]>(`${environment.apiUrl}/temporadas/publico`, { params }))
      .then((res) => this.temporadas.set(res))
      .catch(() => this.temporadas.set([]));
    firstValueFrom(this.http.get<Sucursal[]>(`${environment.apiUrl}/sucursales/publico`, { params }))
      .then((res) => this.sucursales.set(res))
      .catch(() => this.sucursales.set([]));
  });

  protected seleccionarTienda(subdominio: string | null): void {
    this.filtros.seleccionarTienda(subdominio);
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  protected seleccionarTemporada(nombre: string | null): void {
    this.filtros.seleccionarTemporada(nombre);
  }

  protected selectSucursal(nombre: string | null): void {
    this.filtros.seleccionarSucursal(nombre);
  }

  protected selectCategoria(id: string | null): void {
    this.filtros.seleccionarCategoria(id === 'todas' ? null : id);
  }

  protected toggleMarca(nombre: string): void {
    this.filtros.toggleMarca(nombre);
  }

  protected selectTodasMarcas(): void {
    this.filtros.limpiarMarcas();
  }

  private aplicarPrecio(): void {
    const min = this.selectedPrecioMin() === PRECIO_MIN ? null : this.selectedPrecioMin();
    const max = this.selectedPrecioMax() === PRECIO_MAX ? null : this.selectedPrecioMax();
    this.filtros.setPrecio(min, max);
  }

  protected onMinRangeInput(value: string): void {
    const parsed = Math.min(Number(value), this.selectedPrecioMax());
    this.selectedPrecioMin.set(parsed);
    this.aplicarPrecio();
  }

  protected onMaxRangeInput(value: string): void {
    const parsed = Math.max(Number(value), this.selectedPrecioMin());
    this.selectedPrecioMax.set(parsed);
    this.aplicarPrecio();
  }

  protected onMinInputChange(value: string): void {
    const parsed = Math.max(PRECIO_MIN, Math.min(Number(value) || 0, this.selectedPrecioMax()));
    this.selectedPrecioMin.set(parsed);
    this.aplicarPrecio();
  }

  protected onMaxInputChange(value: string): void {
    const parsed = Math.min(PRECIO_MAX, Math.max(Number(value) || 0, this.selectedPrecioMin()));
    this.selectedPrecioMax.set(parsed);
    this.aplicarPrecio();
  }

  protected limpiarFiltros(): void {
    this.selectedPrecioMin.set(PRECIO_MIN);
    this.selectedPrecioMax.set(PRECIO_MAX);
    this.filtros.limpiarTodo();
  }
}
