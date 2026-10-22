import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { ArPrenda, Product } from '../data/products';

interface PrendaArApi {
  url: string;
  ancla_hombro_izq_x: string;
  ancla_hombro_izq_y: string;
  ancla_hombro_der_x: string;
  ancla_hombro_der_y: string;
  ancla_torso_y: string;
}

interface ProductoPublico {
  id: number;
  tienda: string;
  tienda_nombre: string;
  tienda_logo: string | null;
  tienda_color: string;
  nombre: string;
  descripcion: string | null;
  precio: string;
  precio_original: string | null;
  marca_nombre: string;
  categoria_nombre: string;
  temporada_nombre: string;
  imagenes: string[];
  sucursales_disponibles: string[];
  prenda_ar: PrendaArApi | null;
}

export function toArPrenda(raw: PrendaArApi | null): ArPrenda | undefined {
  if (!raw) return undefined;
  return {
    url: raw.url,
    anclaHombroIzqX: Number(raw.ancla_hombro_izq_x),
    anclaHombroIzqY: Number(raw.ancla_hombro_izq_y),
    anclaHombroDerX: Number(raw.ancla_hombro_der_x),
    anclaHombroDerY: Number(raw.ancla_hombro_der_y),
    anclaTorsoY: Number(raw.ancla_torso_y),
  };
}

const PLACEHOLDER_IMAGE = '/img/productos/producto-1.jpg';

// Un producto sin stock en ninguna sucursal no tiene sentido mostrarlo como
// comprable: se sigue listando (para que el cliente lo encuentre) pero
// marcado como agotado en vez de ocultarlo.
export function isAgotado(product: Product): boolean {
  return product.branchesInStock.length === 0;
}

function toProduct(p: ProductoPublico): Product {
  const price = Number(p.precio);
  const originalPrice = p.precio_original ? Number(p.precio_original) : undefined;
  const discountLabel =
    originalPrice && originalPrice > price ? `-${Math.round((1 - price / originalPrice) * 100)}%` : undefined;

  return {
    id: String(p.id),
    tienda: p.tienda,
    tiendaNombre: p.tienda_nombre,
    tiendaLogo: p.tienda_logo,
    tiendaColor: p.tienda_color,
    name: p.nombre,
    brand: p.marca_nombre,
    price,
    originalPrice: discountLabel ? originalPrice : undefined,
    discountLabel,
    image: p.imagenes[0] ?? PLACEHOLDER_IMAGE,
    gallery: p.imagenes.length ? p.imagenes : [PLACEHOLDER_IMAGE],
    category: p.categoria_nombre.toLowerCase(),
    categoryLabel: p.categoria_nombre,
    temporada: p.temporada_nombre,
    isNew: false,
    colors: [],
    sizes: [],
    branchesInStock: p.sucursales_disponibles,
    description: p.descripcion ?? undefined,
    // El backend (ver crear_ar_sesion) usa prenda_ar si existe, si no cae a
    // la primera foto de catalogo, pero solo si es una URL absoluta (subida
    // real a Supabase) -- algunos productos todavia tienen la foto
    // placeholder generica de antes de conectar el backend real (ruta
    // relativa /img/productos/..., no sirve como referencia). El gate del
    // boton tiene que reflejar exactamente ese mismo criterio.
    arPrenda: toArPrenda(p.prenda_ar),
    hasPhotos: !!p.prenda_ar || (p.imagenes[0]?.startsWith('http') ?? false),
  };
}

// Carga el catalogo publico una sola vez y lo comparte entre ShopFilters
// (para derivar categorias/marcas reales) y ProductGrid (para listar y
// filtrar), en vez de que cada componente pida su propia copia.
@Injectable({ providedIn: 'root' })
export class CatalogoPublico {
  private readonly http = inject(HttpClient);
  private cargado = false;

  private readonly todos = signal<Product[]>([]);
  readonly loading = signal(false);

  // Tienda que se está viendo (subdominio): cada boutique muestra solo lo
  // suyo; null = todas (portada de Arlani). La fija cada página.
  readonly tienda = signal<string | null>(null);

  readonly products = computed<Product[]>(() => {
    const tienda = this.tienda();
    return tienda ? this.todos().filter((p) => p.tienda === tienda) : this.todos();
  });

  readonly categorias = computed(() => {
    const vistas = new Map<string, string>();
    for (const p of this.products()) vistas.set(p.category, p.categoryLabel);
    return Array.from(vistas.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  });

  readonly marcas = computed(() => {
    const vistas = new Set<string>();
    for (const p of this.products()) if (p.brand) vistas.add(p.brand);
    return Array.from(vistas).sort((a, b) => a.localeCompare(b));
  });

  // Un producto ya cargado (de cualquier tienda), sin pedirlo al servidor.
  buscar(id: string): Product | undefined {
    return this.todos().find((p) => p.id === id);
  }

  async load(): Promise<void> {
    if (this.cargado) return;
    this.cargado = true;
    this.loading.set(true);
    try {
      const res = await firstValueFrom(this.http.get<ProductoPublico[]>(`${environment.apiUrl}/productos/publico`));
      this.todos.set(res.map(toProduct));
    } catch {
      this.todos.set([]);
    } finally {
      this.loading.set(false);
    }
  }
}
