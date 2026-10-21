import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

interface Enlace {
  texto: string;
  ruta: string;
  fragmento?: string;
}

// Pie de página de la plataforma Arlani Boutiques (portada). Las páginas de
// la tienda Atelier Aranier usan <app-footer>.
@Component({
  selector: 'app-footer-plataforma',
  imports: [RouterLink],
  templateUrl: './footer-plataforma.html',
  styleUrl: './footer-plataforma.scss',
})
export class FooterPlataforma {
  protected readonly anio = new Date().getFullYear();

  protected readonly columnas: { titulo: string; enlaces: Enlace[] }[] = [
    {
      titulo: 'Plataforma',
      enlaces: [
        { texto: 'Por qué Arlani', ruta: '/', fragmento: 'por-que' },
        { texto: 'Funciones', ruta: '/', fragmento: 'funciones' },
        { texto: 'Precios', ruta: '/', fragmento: 'precios' },
      ],
    },
    {
      titulo: 'Para boutiques',
      enlaces: [
        { texto: 'Crear mi boutique', ruta: '/empezar' },
        { texto: 'Iniciar sesión', ruta: '/login' },
      ],
    },
    {
      titulo: 'Boutiques',
      enlaces: [
        { texto: 'Ver todas', ruta: '/', fragmento: 'boutiques' },
        { texto: 'Promociones', ruta: '/', fragmento: 'promociones' },
      ],
    },
  ];
}
