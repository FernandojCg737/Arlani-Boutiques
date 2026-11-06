import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { map } from 'rxjs';
import { LiveSala } from '../../components/live-sala/live-sala';

// CU22: ver un live (/live/:id). Si quien entra es el vendedor de la tienda,
// la misma sala le muestra sus controles.
@Component({
  selector: 'app-live-ver',
  imports: [LiveSala, RouterLink],
  template: `
    <section class="ver">
      <a routerLink="/live" class="ver__volver">← Lives en curso</a>
      <!-- Un live distinto vuelve a crear la sala (y su conexión). -->
      @for (liveId of id() ? [id()!] : []; track liveId) {
        <app-live-sala [liveId]="liveId" />
      }
    </section>
  `,
  styles: `
    .ver { max-width: 1100px; margin: 0 auto; padding: 100px 16px 40px; }
    .ver__volver { display: inline-block; margin-bottom: 14px; font-size: 13px; font-weight: 700; color: #121a2c; text-decoration: none; }
  `,
})
export class LiveVer {
  protected readonly id = toSignal(inject(ActivatedRoute).paramMap.pipe(map((p) => Number(p.get('id')) || null)));
}
