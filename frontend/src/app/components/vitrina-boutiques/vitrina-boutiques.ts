import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CatalogoPublico } from '../../services/catalogo-publico';
import { esLogoOscuro } from '../../services/marca-tienda';
import { enlaceTiendaCorto, rutaTienda } from '../../services/plataforma';
import { TiendaPublicaApi, TiendaResumen } from '../../services/tienda-publica';
import { TIENDA_ORIGINAL } from '../../services/tienda-activa';

interface TarjetaVitrina {
  boutique: string;
  logo: string;
  // Identificador de la tienda: de el salen el enlace que se muestra al pasar
  // el cursor (dominio donde corre la app + /tienda-<subdominio>) y la ruta.
  subdominio: string;
  // Fondo del cartel que tapa la foto al pasar el cursor (color de la marca).
  color: string;
  imagen: string;
  alt: string;
  formato: 'angosta' | 'ancha';
  // Logo oscuro sobre el color de la marca: lleva contorno claro.
  logoOscuro?: boolean;
}

// Vitrina de la portada: las boutiques activas de Arlani. Atelier tiene tres
// tarjetas con fotos de su local; cada boutique nueva suma la suya con su
// color, su logo y la foto de uno de sus productos. Con mas de tres tarjetas
// la fila pasa a ser un carrusel.
@Component({
  selector: 'app-vitrina-boutiques',
  imports: [RouterLink],
  templateUrl: './vitrina-boutiques.html',
  styleUrl: './vitrina-boutiques.scss',
})
export class VitrinaBoutiques {
  protected readonly rutaTienda = rutaTienda;
  protected readonly enlaceTienda = enlaceTiendaCorto;

  // Cada frase se ilumina entera al pasar el cursor por cualquiera de sus
  // palabras; el cierre ("De tu tienda...") queda siempre en blanco.
  protected readonly frases = [
    'Vendé en todos los lugares donde tus clientes compran.',
    'En línea y en mostrador.',
    'En cada sucursal, aunque se caiga internet.',
    'Con reportes de IA y probador virtual.',
  ];

  private readonly api = inject(TiendaPublicaApi);
  private readonly catalogo = inject(CatalogoPublico);
  private readonly tiendas = signal<TiendaResumen[] | null>(null);
  private readonly logosOscuros = signal<Record<string, boolean>>({});

  protected readonly tarjetas = computed<TarjetaVitrina[]>(() => {
    const tiendas = this.tiendas();
    // Sin respuesta del servidor: las tarjetas de Atelier.
    if (!tiendas) return this.tarjetasAtelier;
    const fotos = new Map<string, string>();
    for (const p of this.catalogo.products()) {
      if (p.tienda && !fotos.has(p.tienda) && p.image) fotos.set(p.tienda, p.image);
    }
    const oscuros = this.logosOscuros();
    return tiendas.flatMap((t): TarjetaVitrina[] =>
      t.subdominio === TIENDA_ORIGINAL
        ? this.tarjetasAtelier
        : [
            {
              boutique: t.nombre,
              logo: t.logo_url ?? '',
              subdominio: t.subdominio,
              color: t.color_marca,
              imagen: fotos.get(t.subdominio) ?? '/img/tienda-hero-poster.jpg',
              alt: `Prendas de ${t.nombre}`,
              formato: 'angosta',
              logoOscuro: oscuros[t.subdominio] ?? false,
            },
          ],
    );
  });

  constructor() {
    void this.catalogo.load();
    void this.api
      .listar()
      .then(async (tiendas) => {
        this.tiendas.set(tiendas);
        const oscuros: Record<string, boolean> = {};
        for (const t of tiendas) {
          if (t.logo_url?.startsWith('http')) oscuros[t.subdominio] = await esLogoOscuro(t.logo_url);
        }
        this.logosOscuros.set(oscuros);
      })
      .catch(() => undefined);
  }

  private readonly tarjetasAtelier: TarjetaVitrina[] = [
    {
      boutique: 'Atelier Aranier',
      logo: '/img/logo.png',
      subdominio: 'atelier-aranier',
      color: '#0f1e20',
      imagen: '/img/vitrina/atelier-local.jpg',
      alt: 'Percheros con sacos y pantalones en el local de Atelier Aranier',
      formato: 'angosta',
    },
    {
      boutique: 'Atelier Aranier',
      logo: '/img/logo.png',
      subdominio: 'atelier-aranier',
      color: '#0f1e20',
      imagen: '/img/vitrina/atelier-tienda.jpg',
      alt: 'Catálogo en línea de Atelier Aranier',
      formato: 'ancha',
    },
    {
      boutique: 'Atelier Aranier',
      logo: '/img/logo.png',
      subdominio: 'atelier-aranier',
      color: '#0f1e20',
      imagen: '/img/vitrina/atelier-producto.jpg',
      alt: 'Página de producto de Atelier Aranier con probador de realidad aumentada y reservas',
      formato: 'ancha',
    },
  ];
}
