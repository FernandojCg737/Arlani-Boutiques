import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CatalogoClienteAuto } from '../../services/offline/catalogo-cliente-auto';
import { Sincronizacion } from '../../services/offline/sincronizacion';
import { PaypalSdk } from '../../services/paypal-sdk';
import { mensajeError } from '../../services/plataforma';
import { ComprasPorPagar } from '../../services/offline/compras-por-pagar';

export interface MetodoCompra {
  id: number;
  tipo: 'paypal' | 'qr' | 'transferencia' | 'otro' | 'contra_entrega';
  nombre: string;
  instrucciones: string | null;
  paypal_client_id: string | null;
  qr_url: string | null;
  banco: string | null;
  numero_cuenta: string | null;
  titular: string | null;
}

export interface ItemCompra {
  producto: string;
  talla: string;
  color: string;
  cantidad: number;
  precio_guardado: string;
  precio_actual: string;
  stock: number;
}

export interface CompraOffline {
  id: number;
  uuid: string;
  estado: 'por_pagar' | 'sin_stock' | 'pagada' | 'cancelada';
  mensaje: string | null;
  tienda: string;
  logo_url: string | null;
  color_marca: string | null;
  sucursal: string;
  registrada_en: string;
  entrega: 'retiro' | 'envio';
  direccion: string | null;
  forma_pago: 'en_linea' | 'contra_entrega';
  items: ItemCompra[];
  total_guardado: string;
  total_actual: string;
  total_usd: string;
  precio_cambio: boolean;
  sin_stock: boolean;
  puede_pagar: boolean;
  metodos: MetodoCompra[];
  venta_id: number | null;
}

// Compras hechas sin conexión, al volver la conexión: se revisan contra el
// precio y el stock de AHORA. Sin stock no se puede comprar; si cambió el
// precio se muestra y se paga el actual. Al pagar (PayPal o comprobante) o
// confirmar (contra entrega) se registra la venta, como venta sin conexión.
@Component({
  selector: 'app-pagar-compras',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './pagar-compras.html',
  styleUrls: ['../admin/ventas/ventas.scss', '../admin/sin-conexion/sin-conexion.scss', './pagar-compras.scss'],
})
export class PagarCompras implements OnInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly paypal = inject(PaypalSdk);
  private readonly sync = inject(Sincronizacion);
  private readonly porPagar = inject(ComprasPorPagar);
  private readonly catalogoSinConexion = inject(CatalogoClienteAuto);
  private readonly api = `${environment.apiUrl}/offline/pedidos`;

  protected readonly compras = signal<CompraOffline[]>([]);
  protected readonly hechas = signal<CompraOffline[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly errorDe = signal<Record<string, string>>({});
  protected readonly procesando = signal<string | null>(null);
  protected readonly metodoDe = signal<Record<string, number>>({});
  protected readonly archivoDe = signal<Record<string, File>>({});

  private desmontar: (() => void) | null = null;

  ngOnInit(): void {
    void this.cargar();
  }

  ngOnDestroy(): void {
    this.desmontar?.();
  }

  protected async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set('');
    try {
      this.compras.set(await firstValueFrom(this.http.get<CompraOffline[]>(this.api)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos revisar tus compras: necesitas conexión.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected numero(v: string): number {
    return Number(v);
  }

  protected metodoElegido(c: CompraOffline): MetodoCompra | null {
    const id = this.metodoDe()[c.uuid];
    return c.metodos.find((m) => m.id === id) ?? null;
  }

  protected elegirMetodo(c: CompraOffline, m: MetodoCompra): void {
    this.metodoDe.update((x) => ({ ...x, [c.uuid]: m.id }));
    this.ponerError(c, '');
    this.desmontar?.();
    this.desmontar = null;
    if (m.tipo === 'paypal' && m.paypal_client_id) {
      // El contenedor aparece en el siguiente render.
      setTimeout(() => this.montarPaypal(c, m), 0);
    }
  }

  private montarPaypal(c: CompraOffline, m: MetodoCompra): void {
    const contenedor = document.getElementById(`paypal-${c.uuid}`);
    if (!contenedor || !m.paypal_client_id) return;
    this.desmontar = this.paypal.montarBotones(contenedor, m.paypal_client_id, {
      // Con el boton de PayPal la orden guarda la cuenta: queda autorizada y las
      // proximas compras sin conexion se cobran solas.
      crearOrden: async (fuente?: string) => {
        const r = await firstValueFrom(
          this.http.post<{ order_id: string }>(`${this.api}/${c.uuid}/paypal/orden`, { guardar_paypal: fuente === 'paypal' }),
        );
        return r.order_id;
      },
      aprobar: async (orderId: string) => {
        await this.ejecutar(c, () =>
          firstValueFrom(this.http.post<CompraOffline>(`${this.api}/${c.uuid}/paypal/capturar/${orderId}`, {})),
        );
        // La cuenta quedó autorizada: el catálogo sin conexión lo sabe ya.
        void this.catalogoSinConexion.revisar(true).catch(() => undefined);
      },
      cancelar: () => this.ponerError(c, 'Cancelaste el pago. Puedes intentarlo de nuevo.'),
      error: () => this.ponerError(c, 'Ocurrió un error con PayPal. Intenta de nuevo o elige otro método.'),
    });
  }

  protected alElegirArchivo(c: CompraOffline, ev: Event): void {
    const f = (ev.target as HTMLInputElement).files?.[0];
    if (f) this.archivoDe.update((x) => ({ ...x, [c.uuid]: f }));
  }

  protected async enviarComprobante(c: CompraOffline): Promise<void> {
    const m = this.metodoElegido(c);
    const archivo = this.archivoDe()[c.uuid];
    if (!m || !archivo) {
      this.ponerError(c, 'Sube la foto de tu comprobante de pago.');
      return;
    }
    const datos = new FormData();
    datos.append('metodo_pago_id', String(m.id));
    datos.append('file', archivo);
    await this.ejecutar(c, () => firstValueFrom(this.http.post<CompraOffline>(`${this.api}/${c.uuid}/comprobante`, datos)));
  }

  protected async confirmarContraEntrega(c: CompraOffline): Promise<void> {
    await this.ejecutar(c, () => firstValueFrom(this.http.post<CompraOffline>(`${this.api}/${c.uuid}/contra-entrega`, {})));
  }

  protected async cancelar(c: CompraOffline): Promise<void> {
    if (!confirm(`¿Cancelar la compra en ${c.tienda}?`)) return;
    await this.ejecutar(c, () => firstValueFrom(this.http.post<CompraOffline>(`${this.api}/${c.uuid}/cancelar`, {})));
  }

  private async ejecutar(c: CompraOffline, accion: () => Promise<CompraOffline>): Promise<void> {
    this.procesando.set(c.uuid);
    this.ponerError(c, '');
    try {
      const resultado = await accion();
      this.desmontar?.();
      this.desmontar = null;
      this.compras.update((cs) => cs.filter((x) => x.uuid !== c.uuid));
      if (resultado.estado === 'pagada') this.hechas.update((hs) => [resultado, ...hs]);
      // El dispositivo actualiza su copia y el aviso deja de mostrarse.
      void this.sync.sincronizar();
      void this.porPagar.revisar();
    } catch (err) {
      this.ponerError(c, mensajeError(err, 'No se pudo completar. Revisa tu conexión e intenta de nuevo.'));
      // Puede que el precio o el stock hayan cambiado: se revisa de nuevo.
      void this.cargar();
    } finally {
      this.procesando.set(null);
    }
  }

  private ponerError(c: CompraOffline, msg: string): void {
    this.errorDe.update((x) => ({ ...x, [c.uuid]: msg }));
  }
}
