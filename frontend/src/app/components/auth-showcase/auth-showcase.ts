import { Component, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

// Panel izquierdo de las pantallas de acceso (login, registro, recuperar
// contraseña) con la marca de la plataforma Arlani Boutiques. Cada pantalla
// puede traer su propia foto de fondo (ver frontend/public/img/auth/).
@Component({
  selector: 'app-auth-showcase',
  imports: [RouterLink],
  templateUrl: './auth-showcase.html',
  styleUrl: './auth-showcase.scss',
})
export class AuthShowcase {
  protected readonly fondoPorDefecto = '/img/hero-poster.jpg';

  readonly imagen = input(this.fondoPorDefecto);
  // Qué parte de la foto se ve cuando el panel la recorta (object-position).
  readonly enfoque = input('60% center');

  // Si la foto de la pantalla todavía no existe (o no carga), se usa la del
  // hero en vez de dejar el panel vacío.
  protected readonly fondoFallo = signal(false);
}
