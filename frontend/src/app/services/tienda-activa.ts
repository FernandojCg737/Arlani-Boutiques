import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { BOUTIQUES } from '../data/boutiques';
import { CatalogoPublico } from './catalogo-publico';
import { colorParaTextoBlanco, esLogoOscuro } from './marca-tienda';
import { rutaTienda } from './plataforma';
import { TiendaPublica, TiendaPublicaApi } from './tienda-publica';

// La tienda original, con su sitio completo (inicio en /atelier).
export const TIENDA_ORIGINAL = BOUTIQUES[0].id;

// Boutique que se está visitando (su catálogo, un producto suyo...). Las
// páginas de tienda se pintan con su logo y su color, y su catálogo muestra
// solo sus productos. En las páginas de la plataforma no hay ninguna.
@Injectable({ providedIn: 'root' })
export class TiendaActiva {
  private readonly api = inject(TiendaPublicaApi);
  private readonly catalogo = inject(CatalogoPublico);

  readonly subdominio = signal<string | null>(null);
  readonly tienda = signal<TiendaPublica | null>(null);
  readonly logoOscuro = signal(false);

  readonly esOriginal = computed(() => (this.subdominio() ?? TIENDA_ORIGINAL) === TIENDA_ORIGINAL);
  readonly nombre = computed(() => this.tienda()?.nombre ?? BOUTIQUES[0].nombre);
  readonly logo = computed(() => {
    const t = this.tienda();
    if (t) return t.logo_url;
    return this.esOriginal() ? BOUTIQUES[0].logo : null;
  });
  readonly inicial = computed(() => this.nombre().trim()[0]?.toUpperCase() ?? 'T');
  // Catálogo de la boutique y su "inicio" (Atelier tiene una portada propia).
  readonly rutaCatalogo = computed(() => rutaTienda(this.subdominio() ?? TIENDA_ORIGINAL));
  readonly rutaInicio = computed(() => (this.esOriginal() ? '/atelier' : this.rutaCatalogo()));
  // Sucursal principal (para el pie de página de las boutiques).
  readonly sucursal = computed(() => this.tienda()?.sucursales[0] ?? null);

  constructor() {
    // El color de la tienda reemplaza a --brand-dark en sus páginas.
    effect(() => {
      const t = this.tienda();
      const raiz = document.documentElement.style;
      if (t) raiz.setProperty('--brand-dark', colorParaTextoBlanco(t.color_marca));
      else raiz.removeProperty('--brand-dark');
    });
  }

  // Entra a una boutique: su marca y su catálogo.
  activar(subdominio: string | null): void {
    this.catalogo.tienda.set(subdominio);
    if (subdominio === this.subdominio() && this.tienda()) return;
    this.subdominio.set(subdominio);
    this.tienda.set(null);
    this.logoOscuro.set(false);
    if (!subdominio) return;
    void this.api
      .obtener(subdominio)
      .then((t) => {
        if (this.subdominio() !== subdominio) return;
        this.tienda.set(t);
        return t?.logo_url?.startsWith('http') ? esLogoOscuro(t.logo_url) : false;
      })
      .then((oscuro) => {
        if (this.subdominio() === subdominio) this.logoOscuro.set(!!oscuro);
      })
      .catch(() => undefined);
  }

  // Páginas de la plataforma (portada, carrito, mi cuenta...): sin marca de
  // tienda. No toca el catálogo: cada página fija el suyo.
  salir(): void {
    this.subdominio.set(null);
    this.tienda.set(null);
    this.logoOscuro.set(false);
  }
}
