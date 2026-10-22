import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';
import { filter } from 'rxjs/operators';
import { BOUTIQUES } from '../data/boutiques';
import { CatalogoPublico } from './catalogo-publico';
import { colorParaTextoBlanco, esLogoOscuro } from './marca-tienda';
import { rutaTienda } from './plataforma';
import { TiendaPublica, TiendaPublicaApi } from './tienda-publica';

// La tienda original, con su sitio completo (inicio en /atelier).
export const TIENDA_ORIGINAL = BOUTIQUES[0].id;

// Mientras no se sabe de qué tienda es la página: ni el verde de Atelier ni
// el color de otra tienda, un gris neutro.
const COLOR_NEUTRO = '#2b2b2b';

// Marca de cada tienda ya visitada, guardada en el navegador: la próxima vez
// se pinta al instante y después se actualiza con lo que diga el servidor.
interface MarcaRecordada {
  nombre: string;
  color: string;
  logo: string | null;
  logoOscuro: boolean;
}
const CLAVE_MARCAS = 'arlani_marcas_tiendas';

function leerMarcas(): Record<string, MarcaRecordada> {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_MARCAS) ?? '{}');
  } catch {
    return {};
  }
}

function recordarMarca(subdominio: string, marca: MarcaRecordada): void {
  try {
    localStorage.setItem(CLAVE_MARCAS, JSON.stringify({ ...leerMarcas(), [subdominio]: marca }));
  } catch {
    // Sin localStorage la marca igual llega del servidor, solo que más tarde.
  }
}

// Boutique que se está visitando (su catálogo, un producto suyo...). Las
// páginas de tienda se pintan con su logo y su color, y su catálogo muestra
// solo sus productos. En las páginas de la plataforma no hay ninguna.
@Injectable({ providedIn: 'root' })
export class TiendaActiva {
  private readonly api = inject(TiendaPublicaApi);
  private readonly catalogo = inject(CatalogoPublico);

  // undefined = todavía no se sabe (la página la está cargando); null = sin
  // tienda (se usa la original).
  readonly subdominio = signal<string | null | undefined>(undefined);
  readonly tienda = signal<TiendaPublica | null>(null);
  private readonly recordada = signal<MarcaRecordada | null>(null);
  private readonly logoOscuroCalculado = signal<boolean | null>(null);
  // Una página avisó que va a decir la tienda apenas cargue (ver esperar()).
  private esperando = false;

  readonly esOriginal = computed(() => {
    const s = this.subdominio();
    return s === null || s === TIENDA_ORIGINAL;
  });
  readonly nombre = computed(() => {
    if (this.esOriginal()) return this.tienda()?.nombre ?? BOUTIQUES[0].nombre;
    return this.tienda()?.nombre ?? this.recordada()?.nombre ?? '';
  });
  // Sin dato todavía, null: el encabezado queda sin logo en vez de mostrar otro.
  readonly logo = computed(() => {
    if (this.esOriginal()) return BOUTIQUES[0].logo;
    const t = this.tienda();
    return t ? t.logo_url : (this.recordada()?.logo ?? null);
  });
  readonly logoOscuro = computed(() => this.logoOscuroCalculado() ?? this.recordada()?.logoOscuro ?? false);
  readonly inicial = computed(() => this.nombre().trim()[0]?.toUpperCase() ?? '');
  // Catálogo de la boutique y su "inicio" (Atelier tiene una portada propia).
  readonly rutaCatalogo = computed(() => rutaTienda(this.subdominio() ?? TIENDA_ORIGINAL));
  readonly rutaInicio = computed(() => (this.esOriginal() ? '/atelier' : this.rutaCatalogo()));
  // Sucursal principal (para el pie de página de las boutiques).
  readonly sucursal = computed(() => this.tienda()?.sucursales[0] ?? null);

  constructor() {
    // El color de la tienda reemplaza a --brand-dark en sus páginas.
    effect(() => {
      const raiz = document.documentElement.style;
      if (this.esOriginal()) {
        raiz.removeProperty('--brand-dark');
        return;
      }
      const color = this.tienda()?.color_marca ?? this.recordada()?.color;
      raiz.setProperty('--brand-dark', color ? colorParaTextoBlanco(color) : COLOR_NEUTRO);
    });

    // La dirección ya dice la tienda (/tienda-<subdominio>, /atelier): se
    // activa apenas empieza la navegación, sin esperar al servidor. Si no, la
    // página la dice al abrirse; y si ninguna lo hizo (ej. cotizaciones), se
    // usa la original como antes.
    const router = inject(Router);
    this.porDireccion(location.pathname);
    router.events.pipe(filter((e) => e instanceof NavigationStart)).subscribe((e) => {
      this.esperando = false;
      this.porDireccion(e.url);
    });
    router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {
      if (this.subdominio() === undefined && !this.esperando) this.subdominio.set(null);
    });
  }

  private porDireccion(url: string): void {
    const ruta = url.split(/[?#]/)[0];
    const tienda = /^\/tienda-([a-z0-9][a-z0-9-]{1,38}[a-z0-9])$/.exec(ruta)?.[1];
    if (tienda) this.activar(tienda);
    else if (ruta === '/atelier') this.activar(TIENDA_ORIGINAL);
  }

  // La página sabrá la tienda en un momento (ej. el detalle de un producto
  // mientras lo pide): hasta entonces, encabezado y pie neutros.
  esperar(): void {
    this.esperando = true;
    if (this.subdominio() !== undefined) this.limpiar(undefined);
  }

  // Entra a una boutique: su marca y su catálogo. `conocida` es la marca que
  // ya trae un producto (nombre, color, logo): se pinta sin esperar al servidor.
  activar(subdominio: string | null, conocida?: Omit<MarcaRecordada, 'logoOscuro'>): void {
    this.esperando = false;
    this.catalogo.tienda.set(subdominio);
    if (subdominio === this.subdominio() && this.tienda()) return;
    this.limpiar(subdominio);
    if (!subdominio) return;
    const guardada = leerMarcas()[subdominio];
    this.recordada.set(guardada ?? (conocida ? { ...conocida, logoOscuro: false } : null));
    void this.api
      .obtener(subdominio)
      .then(async (t) => {
        if (this.subdominio() !== subdominio) return;
        this.tienda.set(t);
        if (!t) return;
        const oscuro = t.logo_url?.startsWith('http') ? await esLogoOscuro(t.logo_url) : false;
        if (this.subdominio() !== subdominio) return;
        this.logoOscuroCalculado.set(oscuro);
        recordarMarca(subdominio, { nombre: t.nombre, color: t.color_marca, logo: t.logo_url, logoOscuro: oscuro });
      })
      .catch(() => undefined);
  }

  // Páginas de la plataforma (portada, carrito, mi cuenta...): sin marca de
  // tienda. No toca el catálogo: cada página fija el suyo.
  salir(): void {
    this.esperando = false;
    this.limpiar(null);
  }

  private limpiar(subdominio: string | null | undefined): void {
    this.subdominio.set(subdominio);
    this.tienda.set(null);
    this.recordada.set(null);
    this.logoOscuroCalculado.set(null);
  }
}
