import { Injectable, signal } from '@angular/core';

// La suscripcion de la tienda del usuario vencio (o la tienda fue
// suspendida): el backend responde 402 con X-Suscripcion: vencida y el panel
// solo deja entrar a "Mi suscripcion". Sin dependencias, para que el
// interceptor HTTP pueda usarlo sin ciclos.
@Injectable({ providedIn: 'root' })
export class EstadoTienda {
  readonly vencida = signal(false);
}
