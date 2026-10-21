import { Component } from '@angular/core';
import { Categories } from '../../components/categories/categories';
import { Discounts } from '../../components/discounts/discounts';
import { Hero } from '../../components/hero/hero';
import { InstagramCta } from '../../components/instagram-cta/instagram-cta';
import { NewArrivals } from '../../components/new-arrivals/new-arrivals';
import { Recomendaciones } from '../../components/recomendaciones/recomendaciones';
import { WhatsappCta } from '../../components/whatsapp-cta/whatsapp-cta';

// Inicio de la tienda Atelier Aranier (la primera boutique de Arlani). Es la
// portada original del e-commerce: la raíz "/" ahora es la de la plataforma.
@Component({
  selector: 'app-atelier-inicio',
  imports: [Hero, Categories, InstagramCta, NewArrivals, Recomendaciones, WhatsappCta, Discounts],
  templateUrl: './atelier-inicio.html',
})
export class AtelierInicio {}
