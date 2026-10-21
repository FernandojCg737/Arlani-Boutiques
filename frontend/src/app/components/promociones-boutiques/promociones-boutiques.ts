import { Component, ElementRef, OnInit, computed, inject, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Product } from '../../data/products';
import { CatalogoPublico, isAgotado } from '../../services/catalogo-publico';

// Vitrina de promociones de las boutiques de Arlani: productos con descuento
// del catálogo público (reales, del backend). Por ahora todos son de
// Atelier Aranier, la única boutique; cuando haya más, cada producto traerá
// el nombre de su boutique.
@Component({
  selector: 'app-promociones-boutiques',
  imports: [RouterLink],
  templateUrl: './promociones-boutiques.html',
  styleUrl: './promociones-boutiques.scss',
})
export class PromocionesBoutiques implements OnInit {
  private readonly catalogo = inject(CatalogoPublico);
  private readonly carril = viewChild<ElementRef<HTMLElement>>('carril');

  protected readonly boutique = { nombre: 'Atelier Aranier', logo: '/img/logo.png' };

  // Primero los que tienen stock; los agotados no se ofrecen como promoción.
  protected readonly promociones = computed<Product[]>(() =>
    this.catalogo
      .products()
      .filter((p) => p.discountLabel && !isAgotado(p))
      .slice(0, 10),
  );

  ngOnInit(): void {
    void this.catalogo.load();
  }

  protected desplazar(direccion: 1 | -1): void {
    const carril = this.carril()?.nativeElement;
    if (!carril) return;
    carril.scrollBy({ left: direccion * carril.clientWidth * 0.8, behavior: 'smooth' });
  }
}
