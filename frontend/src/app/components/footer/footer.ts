import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

interface FooterLink {
  label: string;
  path: string;
  fragment?: string;
}

@Component({
  selector: 'app-footer',
  imports: [RouterLink],
  templateUrl: './footer.html',
  styleUrl: './footer.scss',
})
export class Footer {
  protected readonly year = new Date().getFullYear();

  protected readonly exploreLinks: FooterLink[] = [
    { label: 'Productos', path: '/tienda-atelier-aranier' },
    { label: 'Novedades', path: '/atelier', fragment: 'novedades' },
    { label: 'Descuentos', path: '/atelier', fragment: 'descuentos' },
    { label: 'Soporte', path: '/contacto' },
  ];

  protected readonly legalLinks: FooterLink[] = [
    { label: 'Terminos', path: '/terminos' },
    { label: 'Privacidad', path: '/privacidad' },
    { label: 'Envios', path: '/envios' },
  ];

  // TODO: reemplazar con los datos reales de contacto de la tienda.
  protected readonly email = 'contacto@atelieraranier.com';
  protected readonly phoneDisplay = '+591 73766956';
  protected readonly phoneHref = '59173766956';
  protected readonly address = 'Av. San Martin, 3er Anillo Interno, Equipetrol, Santa Cruz de la Sierra, Bolivia';

  protected readonly instagramUrl = 'https://instagram.com/';
  protected readonly facebookUrl = 'https://facebook.com/';
}
