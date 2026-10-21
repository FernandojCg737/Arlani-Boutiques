import { Component, ElementRef, OnDestroy, afterNextRender, inject, signal, viewChildren } from '@angular/core';

interface Paso {
  etiqueta: string;
  titulo: string;
  texto: string;
}

// "Por qué Arlani": relato con scroll. A la izquierda pasan los tres tipos de
// boutique; a la derecha una escena fija cambia según el paso que está en el
// centro de la pantalla (y vuelve a animarse cada vez que se activa).
@Component({
  selector: 'app-por-que-arlani',
  templateUrl: './por-que-arlani.html',
  styleUrl: './por-que-arlani.scss',
})
export class PorQueArlani implements OnDestroy {
  private readonly pasosDom = viewChildren<ElementRef<HTMLElement>>('paso');
  private observador?: IntersectionObserver;

  protected readonly activo = signal(0);

  protected readonly pasos: Paso[] = [
    {
      etiqueta: 'Para boutiques que recién empiezan',
      titulo: 'Abrí tu tienda online en una tarde.',
      texto:
        'Subí tus prendas con fotos, tallas y colores, elegí los colores de tu marca y listo: tus clientes ya pueden comprar, reservar y probarse la ropa con realidad aumentada.',
    },
    {
      etiqueta: 'Para cadenas con varias sucursales',
      titulo: 'Cada sucursal, en un solo panel.',
      texto:
        'Stock por sucursal y por talla, ventas del día y empleados con permisos según su cargo. Comparás tus sucursales sin pedirle planillas a nadie.',
    },
    {
      etiqueta: 'Para tiendas con mala señal',
      titulo: 'Si se corta internet, la caja sigue.',
      texto:
        'Cada venta se guarda en el dispositivo y se sincroniza sola cuando vuelve la conexión. Sin ventas perdidas y sin ventas repetidas.',
    },
  ];

  // Datos de muestra para las escenas (son ilustrativos, no del backend).
  protected readonly productos = [
    { nombre: 'Polera negra', precio: 120, imagen: '/img/productos/producto-1.jpg' },
    { nombre: 'Polera blanca', precio: 110, imagen: '/img/productos/producto-2.jpg' },
    { nombre: 'Chaqueta de cuero', precio: 450, imagen: '/img/productos/producto-4.jpg' },
  ];

  protected readonly sucursales = [
    { nombre: 'Equipetrol', monto: 5240, porcentaje: 100 },
    { nombre: 'Las Palmas', monto: 4180, porcentaje: 80 },
    { nombre: 'Norte', monto: 3060, porcentaje: 58 },
  ];

  protected readonly ventasSinConexion = [
    { numero: 1024, prenda: 'Camisa Oxford', monto: 165 },
    { numero: 1025, prenda: 'Chompa básica', monto: 224 },
    { numero: 1026, prenda: 'Gorra clásica', monto: 96 },
  ];

  protected readonly totalSucursales = this.sucursales.reduce((suma, s) => suma + s.monto, 0);

  constructor() {
    afterNextRender(() => {
      // Un paso se activa cuando cruza una franja fina de la pantalla: al
      // centro en escritorio; en celular más abajo, porque la escena fija
      // ocupa la parte de arriba y taparía el texto del paso.
      const escritorio = window.matchMedia('(min-width: 960px)').matches;
      this.observador = new IntersectionObserver(
        (entradas) => {
          for (const entrada of entradas) {
            if (!entrada.isIntersecting) continue;
            const indice = this.pasosDom().findIndex((p) => p.nativeElement === entrada.target);
            if (indice >= 0) this.activo.set(indice);
          }
        },
        { rootMargin: escritorio ? '-45% 0px -45% 0px' : '-70% 0px -25% 0px' },
      );
      for (const paso of this.pasosDom()) this.observador.observe(paso.nativeElement);
    });
  }

  ngOnDestroy(): void {
    this.observador?.disconnect();
  }
}
