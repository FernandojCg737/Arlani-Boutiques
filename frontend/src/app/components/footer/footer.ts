import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TiendaActiva } from '../../services/tienda-activa';

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
// Pie de las paginas de tienda: con la marca y los datos de la boutique que
// se esta visitando (Atelier mantiene sus datos de contacto propios).
export class Footer {
  protected readonly tienda = inject(TiendaActiva);
  protected readonly year = new Date().getFullYear();

  protected readonly exploreLinks = computed<FooterLink[]>(() =>
    this.tienda.esOriginal()
      ? [
          { label: 'Productos', path: this.tienda.rutaCatalogo() },
          { label: 'Novedades', path: '/atelier', fragment: 'novedades' },
          { label: 'Descuentos', path: '/atelier', fragment: 'descuentos' },
          { label: 'Soporte', path: '/contacto' },
        ]
      : [
          { label: 'Productos', path: this.tienda.rutaCatalogo() },
          { label: 'Otras boutiques', path: '/', fragment: 'boutiques' },
        ],
  );

  protected readonly descripcion = computed(() => {
    if (this.tienda.esOriginal())
      return 'Ropa premium para el hombre moderno en Bolivia. Estilo, calidad y actitud, directo a tu puerta.';
    const ciudad = this.tienda.tienda()?.ciudad;
    return `Boutique${ciudad ? ' de ' + ciudad : ''} que vende en línea con Arlani Boutiques.`;
  });
  // Direccion y telefono: los de Atelier, o los de la sucursal principal.
  protected readonly direccion = computed(() => {
    if (this.tienda.esOriginal()) return this.address;
    const s = this.tienda.sucursal();
    return s ? `${s.direccion}, ${s.ciudad}` : null;
  });
  protected readonly telefono = computed(() =>
    this.tienda.esOriginal() ? this.phoneDisplay : (this.tienda.sucursal()?.telefono ?? null),
  );

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
