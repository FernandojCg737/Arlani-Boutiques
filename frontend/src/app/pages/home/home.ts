import { Component } from '@angular/core';
import { CarruselBoutiques } from '../../components/carrusel-boutiques/carrusel-boutiques';
import { CtaFinal } from '../../components/cta-final/cta-final';
import { FuncionesPlataforma } from '../../components/funciones-plataforma/funciones-plataforma';
import { Hero } from '../../components/hero/hero';
import { PorQueArlani } from '../../components/por-que-arlani/por-que-arlani';
import { PreciosPlanes } from '../../components/precios-planes/precios-planes';
import { PromocionesBoutiques } from '../../components/promociones-boutiques/promociones-boutiques';
import { VitrinaBoutiques } from '../../components/vitrina-boutiques/vitrina-boutiques';

// Portada de la plataforma Arlani Boutiques. El inicio de la tienda Atelier
// Aranier (novedades, descuentos, Instagram...) vive ahora en /atelier.
@Component({
  selector: 'app-home',
  imports: [
    Hero,
    VitrinaBoutiques,
    PromocionesBoutiques,
    FuncionesPlataforma,
    PorQueArlani,
    PreciosPlanes,
    CtaFinal,
    CarruselBoutiques,
  ],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  // Completan "TU BOUTIQUE PUEDE SER…" en el hero (van rotando).
  protected readonly frasesHero = ['online', 'imparable', 'inteligente', 'multisucursal', 'tendencia'];
}
