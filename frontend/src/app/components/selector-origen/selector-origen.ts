import { Component, input, output } from '@angular/core';

export type Origen = 'online' | 'offline';

// ONLINE / OFFLINE de las ventas y reservas de una tienda (CU05 y CU06 del
// SuperAdministrador): las registradas con conexion y las que llegaron al
// servidor al sincronizar el modo sin conexion (CU12).
@Component({
  selector: 'app-selector-origen',
  template: `
    <div class="origen" role="tablist" [attr.aria-label]="'Origen de las ' + que()">
      <button type="button" role="tab" [attr.aria-selected]="origen() === 'online'" [class.is-activo]="origen() === 'online'"
              (click)="cambio.emit('online')">
        <strong>ONLINE</strong>
        <small>{{ que() === 'ventas' ? 'Compras registradas con conexión: tienda en línea y mostrador' : 'Reservas hechas con conexión' }}</small>
      </button>
      <button type="button" role="tab" [attr.aria-selected]="origen() === 'offline'" [class.is-activo]="origen() === 'offline'"
              (click)="cambio.emit('offline')">
        <strong>OFFLINE</strong>
        <small>{{ que() === 'ventas' ? 'Compras' : 'Reservas' }} hechas sin conexión y sincronizadas (CU12)</small>
      </button>
    </div>
  `,
  styles: `
    :host { display: block; margin: 0 0 20px; }
    .origen { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; max-width: 720px; }
    button {
      display: flex; flex-direction: column; gap: 4px; padding: 14px 16px;
      border: 1px solid #ddd; background: #fff; font: inherit; text-align: left; cursor: pointer;
    }
    strong { font-size: 14px; font-weight: 800; letter-spacing: 0.06em; color: var(--brand-dark, #1f2a44); }
    small { font-size: 12px; color: #777; }
    button.is-activo { border-color: var(--brand-dark, #1f2a44); box-shadow: inset 0 0 0 1px var(--brand-dark, #1f2a44); }
    button:hover:not(.is-activo) { border-color: #bbb; }
  `,
})
export class SelectorOrigen {
  readonly origen = input<Origen>('online');
  readonly que = input<'ventas' | 'reservas'>('ventas');
  readonly cambio = output<Origen>();
}
