import { DecimalPipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { ComprasPorPagar } from '../../services/offline/compras-por-pagar';
import { Sincronizacion } from '../../services/offline/sincronizacion';

// Aviso con prioridad: al volver la conexión, si el cliente tiene compras
// hechas sin conexión por pagar (o que se quedaron sin stock), se le muestra
// encima de cualquier página para que las revise y pague.
// Antes que eso, el resultado de las compras pagadas con el PayPal guardado:
// "Pago finalizado con éxito" o "Pago no finalizado" con cada prenda que no
// se cobró y por qué.
@Component({
  selector: 'app-aviso-compras',
  imports: [DecimalPipe],
  template: `
    @if (sync.cobros().length) {
      <div class="aviso-fondo" role="dialog" aria-modal="true" aria-labelledby="aviso-cobro-titulo">
        <div class="aviso" [class.is-exito]="todoCobrado()">
          <span class="aviso__eyebrow">Tu PayPal guardado</span>
          <h2 id="aviso-cobro-titulo">{{ todoCobrado() ? 'Pago finalizado con éxito' : 'Pago no finalizado' }}</h2>
          <ul>
            @for (c of sync.cobros(); track c.uuid) {
              <li>
                <strong>{{ c.empresa_nombre }} · {{ c.sucursal_nombre }}</strong>
                <span>{{ c.total_cobrado ? 'Bs ' + (c.total_cobrado | number: '1.2-2') : 'Bs 0,00' }}</span>
                @if (c.estado === 'pagada') {
                  <small>Se cobró todo{{ c.venta_id ? ' · Venta #' + c.venta_id : '' }}</small>
                } @else {
                  <small class="is-mal">
                    {{ c.estado === 'pago_parcial' ? 'Se cobró solo lo disponible. No se pudo pagar:' : 'No se te cobró nada:' }}
                  </small>
                  @for (n of c.no_pagados ?? []; track $index) {
                    <small class="is-detalle"><b>{{ n.producto }} ({{ n.talla }}, {{ n.color }})</b> · {{ n.motivo }}</small>
                  } @empty {
                    <small class="is-detalle">{{ c.mensaje }}</small>
                  }
                }
              </li>
            }
          </ul>
          @if (!todoCobrado()) {
            <p>Lo que no se pudo pagar no se te cobró. Puedes volver a comprarlo cuando haya stock.</p>
          }
          <div class="aviso__acciones">
            <button type="button" (click)="sync.marcarCobrosVistos()">Entendido</button>
          </div>
        </div>
      </div>
    } @else if (servicio.mostrarAviso() && !enPagina()) {
      <div class="aviso-fondo" role="dialog" aria-modal="true" aria-labelledby="aviso-compras-titulo">
        <div class="aviso">
          <span class="aviso__eyebrow">Volviste a tener conexión</span>
          <h2 id="aviso-compras-titulo">Tienes compras sin conexión por completar</h2>
          <ul>
            @for (c of servicio.compras(); track c.uuid) {
              <li>
                <strong>{{ c.tienda }}</strong>
                <span>Bs {{ c.total_actual | number: '1.2-2' }}</span>
                @if (c.sin_stock) {
                  <small class="is-mal">Ya no hay stock: no se puede comprar</small>
                } @else if (c.precio_cambio) {
                  <small class="is-ojo">Cambió el precio</small>
                } @else {
                  <small>Lista para pagar</small>
                }
              </li>
            }
          </ul>
          <p>Revisamos el precio y el stock de ahora antes de que pagues.</p>
          <div class="aviso__acciones">
            <button type="button" class="is-secundario" (click)="servicio.posponer()">Más tarde</button>
            <button type="button" (click)="irAPagar()">Revisar y pagar</button>
          </div>
        </div>
      </div>
    }
  `,
  styles: `
    .aviso-fondo {
      position: fixed;
      inset: 0;
      z-index: 2000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      background: rgba(15, 20, 35, 0.6);
    }
    .aviso {
      width: 100%;
      max-width: 440px;
      padding: 26px;
      background: #fff;
      border-top: 4px solid #c4503d;
      font-family: inherit;
    }
    .aviso__eyebrow {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #c4503d;
    }
    h2 {
      margin: 6px 0 14px;
      font-size: 19px;
      line-height: 1.25;
      color: #1f2a44;
    }
    ul {
      margin: 0 0 12px;
      padding: 0;
      list-style: none;
    }
    li {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 2px 12px;
      padding: 9px 0;
      border-bottom: 1px solid #eee;
      font-size: 14px;
    }
    li small {
      grid-column: 1 / -1;
      font-size: 12px;
      color: #2e7d32;
    }
    li small.is-mal {
      color: #b3261e;
    }
    li small.is-ojo {
      color: #b26a00;
    }
    li small.is-detalle {
      color: #444;
      line-height: 1.4;
    }
    .aviso.is-exito {
      border-top-color: #2e7d32;
    }
    p {
      margin: 0 0 16px;
      font-size: 13px;
      color: #666;
    }
    .aviso__acciones {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    button {
      border: none;
      background: #1f2a44;
      color: #fff;
      padding: 11px 18px;
      font: inherit;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: pointer;
    }
    button.is-secundario {
      background: #fff;
      color: #1f2a44;
      border: 1px solid #ddd;
    }
  `,
})
export class AvisoCompras {
  protected readonly servicio = inject(ComprasPorPagar);
  protected readonly sync = inject(Sincronizacion);
  protected readonly todoCobrado = computed(() => this.sync.cobros().every((c) => c.estado === 'pagada'));
  private readonly router = inject(Router);

  protected enPagina(): boolean {
    return this.router.url.startsWith('/pagar-compras');
  }

  protected irAPagar(): void {
    void this.router.navigateByUrl('/pagar-compras');
  }
}
