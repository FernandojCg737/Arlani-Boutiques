import { DatePipe, Location } from '@angular/common';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { LiveApi, LiveResumen, fechaUtc } from '../../services/live';

// CU22: los lives en curso de todas las tiendas (botón LIVE de la portada).
@Component({
  selector: 'app-live-lista',
  imports: [DatePipe, RouterLink],
  template: `
    <section class="lives">
      <button type="button" class="lives__volver" (click)="volver()">← Volver</button>
      <header>
        <span class="lives__eyebrow">Arlani Live</span>
        <h1>Compra en vivo</h1>
        <p>Las boutiques muestran sus prendas en directo: mira, pregunta en los comentarios y agrégalas a tu carrito sin salir del live.</p>
      </header>
      @if (cargando()) {
        <p class="lives__vacio">Buscando lives…</p>
      } @else {
        <div class="lives__grilla">
          @for (l of lives(); track l.id) {
            <a class="lives__tarjeta" [routerLink]="['/live', l.id]" [style.--marca]="l.color_marca || '#121a2c'">
              <div class="lives__portada">
                @if (l.logo_url) {
                  <img [src]="l.logo_url" [alt]="l.tienda" />
                } @else {
                  <span class="lives__inicial">{{ l.tienda.charAt(0) }}</span>
                }
                <span class="lives__badge">EN VIVO</span>
                <span class="lives__vistas">👁 {{ l.espectadores }}</span>
              </div>
              <div class="lives__info">
                <strong>{{ l.titulo }}</strong>
                <span>{{ l.tienda }} · desde las {{ fechaUtc(l.inicio) | date: 'HH:mm' }}</span>
              </div>
            </a>
          } @empty {
            <p class="lives__vacio">Ninguna boutique está en vivo ahora. Te avisaremos en tus notificaciones cuando alguna empiece.</p>
          }
        </div>
      }
    </section>
  `,
  styles: `
    .lives { max-width: 1100px; margin: 0 auto; padding: 120px 20px 80px; color: #121a2c; }
    header { margin-bottom: 28px; }
    .lives__volver { display: inline-flex; align-items: center; margin: 0 0 18px; padding: 4px 0; border: none; background: none;
      font: inherit; font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #121a2c; cursor: pointer; }
    .lives__volver:hover { text-decoration: underline; }
    .lives__eyebrow { font-size: 12px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: #e5292f; }
    h1 { margin: 6px 0 8px; font-size: clamp(28px, 4vw, 40px); }
    header p { margin: 0; max-width: 620px; color: #5f6779; line-height: 1.5; }
    .lives__grilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 18px; }
    .lives__tarjeta { display: block; text-decoration: none; color: inherit; background: #fff; border-radius: 14px; overflow: hidden;
      box-shadow: 0 1px 3px rgba(18, 26, 44, 0.08); transition: transform 0.2s ease-out, box-shadow 0.2s ease-out; }
    .lives__tarjeta:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(18, 26, 44, 0.12); }
    .lives__portada { position: relative; aspect-ratio: 4 / 5; display: grid; place-items: center; background: var(--marca); }
    .lives__portada img { width: 55%; max-height: 55%; object-fit: contain; filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.25)); }
    .lives__inicial { font-size: 64px; font-weight: 800; color: #fff; }
    .lives__badge { position: absolute; top: 10px; left: 10px; padding: 3px 8px; border-radius: 4px; background: #e5292f; color: #fff;
      font-size: 11px; font-weight: 800; letter-spacing: 0.06em; }
    .lives__vistas { position: absolute; top: 10px; right: 10px; padding: 3px 8px; border-radius: 4px; background: rgba(0, 0, 0, 0.45);
      color: #fff; font-size: 12px; }
    .lives__info { padding: 12px 14px; display: flex; flex-direction: column; gap: 3px; }
    .lives__info span { font-size: 13px; color: #5f6779; }
    .lives__vacio { color: #5f6779; }
  `,
})
export class LiveLista implements OnInit, OnDestroy {
  private readonly api = inject(LiveApi);
  private readonly location = inject(Location);
  private readonly router = inject(Router);
  private intervalo: ReturnType<typeof setInterval> | null = null;
  protected readonly fechaUtc = fechaUtc;
  protected readonly lives = signal<LiveResumen[]>([]);
  protected readonly cargando = signal(true);

  async ngOnInit(): Promise<void> {
    this.lives.set(await this.api.revisarEnVivo());
    this.cargando.set(false);
    this.intervalo = setInterval(async () => this.lives.set(await this.api.revisarEnVivo()), 20000);
  }

  // A la página anterior; si se entró directo a los lives, al inicio.
  protected volver(): void {
    if (window.history.length > 1) this.location.back();
    else void this.router.navigateByUrl('/');
  }

  ngOnDestroy(): void {
    if (this.intervalo) clearInterval(this.intervalo);
  }
}
