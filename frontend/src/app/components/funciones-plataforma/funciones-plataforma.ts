import { Component, ElementRef, OnDestroy, afterNextRender, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

// Sección "Funciones" de la portada: tres tarjetas animadas con lo que hace la
// plataforma (tienda con tu marca, panel de todas las sucursales y ventas sin
// internet). Las animaciones solo corren mientras la sección está en pantalla.
@Component({
  selector: 'app-funciones-plataforma',
  imports: [RouterLink],
  templateUrl: './funciones-plataforma.html',
  styleUrl: './funciones-plataforma.scss',
})
export class FuncionesPlataforma implements OnDestroy {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private observador?: IntersectionObserver;

  protected readonly enVista = signal(false);

  // Etiquetas que orbitan en los anillos del panel; se encienden de a una.
  protected readonly modulos = [
    { nombre: 'Inventario', x: 50, y: 9 },
    { nombre: 'Ventas', x: 84, y: 26 },
    { nombre: 'Reservas', x: 86, y: 70 },
    { nombre: 'Pagos', x: 62, y: 90 },
    { nombre: 'Empleados', x: 24, y: 88 },
    { nombre: 'Sucursales', x: 13, y: 50 },
    { nombre: 'Reportes IA', x: 22, y: 16 },
  ];

  constructor() {
    afterNextRender(() => {
      this.observador = new IntersectionObserver(
        ([entrada]) => this.enVista.set(entrada.isIntersecting),
        { threshold: 0.15 },
      );
      this.observador.observe(this.host.nativeElement);
    });
  }

  ngOnDestroy(): void {
    this.observador?.disconnect();
  }
}
