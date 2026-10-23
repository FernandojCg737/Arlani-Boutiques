import { Injectable, inject } from '@angular/core';
import { NavigationStart, Router } from '@angular/router';
import { SwUpdate, VersionReadyEvent } from '@angular/service-worker';
import { filter } from 'rxjs/operators';

const REVISAR_CADA_MS = 10 * 60_000;

// PWA: el service worker guarda la app para abrirla sin conexión, y por eso
// después de un despliegue seguiría mostrando la versión anterior. Aquí se
// busca la versión nueva (al abrir, al volver a la pestaña y cada 10 min) y,
// cuando ya está descargada, se aplica en la próxima navegación: así no se
// recarga en medio de un formulario o de un pago.
@Injectable({ providedIn: 'root' })
export class ActualizacionApp {
  private readonly sw = inject(SwUpdate);
  private readonly router = inject(Router);
  private lista = false;

  constructor() {
    if (!this.sw.isEnabled) return;
    this.sw.versionUpdates
      .pipe(filter((e): e is VersionReadyEvent => e.type === 'VERSION_READY'))
      .subscribe(() => (this.lista = true));
    this.router.events.pipe(filter((e) => e instanceof NavigationStart)).subscribe((e) => {
      if (this.lista) window.location.href = (e as NavigationStart).url;
    });
    this.revisar();
    setInterval(() => this.revisar(), REVISAR_CADA_MS);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') this.revisar();
    });
  }

  private revisar(): void {
    if (navigator.onLine) this.sw.checkForUpdate().catch(() => undefined);
  }
}
