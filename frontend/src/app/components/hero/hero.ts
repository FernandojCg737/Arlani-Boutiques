import { AfterViewInit, Component, ElementRef, OnDestroy, input, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';

// Tiempo que cada frase rotativa queda visible, y duracion de su salida
// (igual a la transicion de .hero-frase en hero.scss).
const INTERVALO_FRASE_MS = 2800;
const SALIDA_FRASE_MS = 600;

@Component({
  selector: 'app-hero',
  imports: [RouterLink],
  templateUrl: './hero.html',
  styleUrl: './hero.scss',
})
export class Hero implements AfterViewInit, OnDestroy {
  readonly videoSrc = input('/video/hero.mp4');
  readonly posterSrc = input('/img/hero-poster.jpg');
  readonly eyebrow = input('LA TIENDA #1 DE ROPA PARA HOMBRES EN BOLIVIA');
  readonly title = input('ESTILO QUE SE NOTA');
  readonly subtitle = input('Prendas pensadas para el hombre que no pasa desapercibido.');
  readonly showCta = input(true);
  readonly align = input<'left' | 'center'>('left');
  readonly size = input<'full' | 'half'>('full');

  // Opcional: si se pasan frases, el titulo queda "title" + una frase que va
  // cambiando debajo (ej. "TU BOUTIQUE PUEDE SER" + "IMPARABLE"...).
  readonly frasesRotativas = input<string[]>([]);

  // Textos y destinos de los dos botones (por defecto, los de la tienda).
  readonly ctaPrincipalTexto = input('Ir a tienda');
  readonly ctaPrincipalRuta = input('/tienda-atelier-aranier');
  readonly ctaPrincipalFragmento = input<string | undefined>(undefined);
  readonly ctaSecundarioTexto = input('Explorar coleccion');
  readonly ctaSecundarioRuta = input('/tienda-atelier-aranier');
  readonly ctaSecundarioFragmento = input<string | undefined>(undefined);

  protected readonly fraseActual = signal(0);
  protected readonly fraseSaliente = signal<number | null>(null);
  private temporizador?: ReturnType<typeof setInterval>;

  private readonly videoRef = viewChild<ElementRef<HTMLVideoElement>>('heroVideo');

  ngAfterViewInit(): void {
    const video = this.videoRef()?.nativeElement;
    if (video) {
      // No usamos el atributo HTML "autoplay": compite con esta llamada y el
      // navegador puede interrumpir una a la otra, dejando el video trabado en
      // pausa. Se controla 100% por codigo: forzamos muted como propiedad (no
      // solo atributo) porque algunos navegadores lo exigen justo antes de
      // play() para permitir el autoplay sin gesto del usuario.
      video.muted = true;
      video.play().catch(() => {
        // Si aun asi el navegador lo bloquea, no pasa nada visualmente: queda
        // el degradado de fondo del hero.
      });
    }

    // Con "reducir movimiento" la frase queda fija en la primera.
    const reducir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (this.frasesRotativas().length > 1 && !reducir) {
      this.temporizador = setInterval(() => this.siguienteFrase(), INTERVALO_FRASE_MS);
    }
  }

  ngOnDestroy(): void {
    clearInterval(this.temporizador);
  }

  private siguienteFrase(): void {
    const anterior = this.fraseActual();
    this.fraseSaliente.set(anterior);
    this.fraseActual.set((anterior + 1) % this.frasesRotativas().length);
    setTimeout(() => {
      if (this.fraseSaliente() === anterior) this.fraseSaliente.set(null);
    }, SALIDA_FRASE_MS);
  }
}
