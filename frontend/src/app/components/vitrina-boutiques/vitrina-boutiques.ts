import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { enlaceTiendaCorto, rutaTienda } from '../../services/plataforma';

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
}

// Vitrina de la portada: tiendas reales hechas con Arlani. Por ahora la única
// boutique es Atelier Aranier; cuando se sumen más empresas basta con agregar
// sus tarjetas acá.
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

  protected readonly tarjetas: TarjetaVitrina[] = [
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
