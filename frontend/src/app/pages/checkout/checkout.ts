import { DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { AfterViewInit, Component, ElementRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Cart, DetalleCarrito } from '../../services/cart';
import { PaypalSdk } from '../../services/paypal-sdk';

interface StockItem {
  detalle_id: number;
  producto_id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  sucursal_id: number;
  sucursal_nombre: string;
  cantidad_pedida: number;
  cantidad_disponible: number;
  disponible: boolean;
}

interface VentaCreada {
  id: number;
  sucursal_nombre: string;
}

type Metodo = 'paypal' | 'qr';
type Estado = 'cargando' | 'formulario' | 'procesando' | 'listo' | 'listo-qr' | 'error' | 'vacio';

// CU11: checkout del carrito. El pago con PayPal/tarjeta se cobra solo (el
// SDK de PayPal muestra su propio boton, que llama a nuestro backend para
// crear y despues capturar la orden); el pago por QR sube un comprobante y
// queda pendiente de que un cajero/encargado lo revise.
//
// La sucursal de retiro de CADA producto se elige al agregarlo al carrito
// (pedido explicito del usuario), no aca -- si el carrito termina con
// productos de sucursales distintas, un solo pago (PayPal o QR) se reparte
// en varias ventas, una por sucursal.
@Component({
  selector: 'app-checkout',
  imports: [RouterLink, DecimalPipe],
  templateUrl: './checkout.html',
  styleUrl: './checkout.scss',
})
export class Checkout implements OnInit, AfterViewInit {
  protected readonly cart = inject(Cart);
  private readonly http = inject(HttpClient);
  private readonly paypalSdk = inject(PaypalSdk);
  private readonly router = inject(Router);

  private readonly paypalContainer = viewChild<ElementRef<HTMLDivElement>>('paypalContainer');

  protected readonly estado = signal<Estado>('cargando');
  protected readonly metodo = signal<Metodo>('paypal');
  protected readonly errorMsg = signal('');
  protected readonly archivoComprobante = signal<File | null>(null);
  protected readonly stockStatus = signal<StockItem[] | null>(null);
  protected readonly verificandoStock = signal(false);
  protected readonly ventasCreadas = signal<VentaCreada[]>([]);

  // Chequeo proactivo (pedido del usuario): antes esto solo se descubria
  // recien al aprobar el pago en PayPal o subir el comprobante QR. Cada
  // item del carrito ya trae su propia sucursal (elegida al agregarlo), asi
  // que esto solo re-confirma que el stock siga estando.
  protected readonly itemsSinStock = computed(() => this.stockStatus()?.filter((i) => !i.disponible) ?? []);
  protected readonly stockOk = computed(() => this.stockStatus() !== null && this.itemsSinStock().length === 0);

  // Agrupa el resumen del carrito por sucursal de retiro, para que el
  // cliente vea claramente si su pedido se va a repartir en mas de un lugar.
  protected readonly gruposPorSucursal = computed(() => {
    const grupos = new Map<string, { sucursal_nombre: string; items: DetalleCarrito[] }>();
    for (const item of this.cart.items()) {
      const existente = grupos.get(item.sucursal_nombre);
      if (existente) {
        existente.items.push(item);
      } else {
        grupos.set(item.sucursal_nombre, { sucursal_nombre: item.sucursal_nombre, items: [item] });
      }
    }
    return [...grupos.values()];
  });

  private botonesPaypalRenderizados = false;

  ngOnInit(): void {
    void this.cargar();
  }

  ngAfterViewInit(): void {
    // Se intenta renderizar el boton de PayPal cada vez que Angular
    // actualiza la vista; si ya esta renderizado o todavia no corresponde
    // mostrarlo, renderizarBotonPaypal() no hace nada.
    void this.renderizarBotonPaypal();
  }

  private async cargar(): Promise<void> {
    await this.cart.cargar();
    if (this.cart.items().length === 0) {
      this.estado.set('vacio');
      return;
    }
    this.estado.set('formulario');
    void this.verificarStock();
  }

  private async verificarStock(): Promise<void> {
    this.verificandoStock.set(true);
    try {
      const res = await firstValueFrom(
        this.http.get<StockItem[]>(`${environment.apiUrl}/ventas/checkout/verificar-stock`),
      );
      this.stockStatus.set(res);
    } catch {
      // Si falla el chequeo, no bloqueamos el pago con esto -- la validacion
      // real y definitiva sigue estando del lado del backend al capturar.
      this.stockStatus.set([]);
    } finally {
      this.verificandoStock.set(false);
      this.botonesPaypalRenderizados = false;
      void this.renderizarBotonPaypal();
    }
  }

  protected onMetodoChange(m: Metodo): void {
    this.metodo.set(m);
    if (m === 'paypal') {
      this.botonesPaypalRenderizados = false;
      setTimeout(() => void this.renderizarBotonPaypal());
    }
  }

  private async renderizarBotonPaypal(): Promise<void> {
    if (this.metodo() !== 'paypal' || this.estado() !== 'formulario' || !this.stockOk()) return;
    if (this.botonesPaypalRenderizados) return;
    const contenedor = this.paypalContainer()?.nativeElement;
    if (!contenedor) return;

    this.botonesPaypalRenderizados = true;
    contenedor.innerHTML = '';

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const paypal = (await this.paypalSdk.cargar()) as any;
      paypal
        .Buttons({
          createOrder: async () => {
            const res = await firstValueFrom(
              this.http.post<{ order_id: string }>(`${environment.apiUrl}/ventas/checkout/paypal/crear-orden`, {}),
            );
            return res.order_id;
          },
          onApprove: async (data: { orderID: string }) => {
            this.estado.set('procesando');
            try {
              const ventas = await firstValueFrom(
                this.http.post<VentaCreada[]>(`${environment.apiUrl}/ventas/checkout/paypal/capturar/${data.orderID}`, {}),
              );
              this.ventasCreadas.set(ventas);
              this.estado.set('listo');
            } catch (err) {
              this.errorMsg.set(this.extraerError(err));
              this.estado.set('formulario');
              this.botonesPaypalRenderizados = false;
              setTimeout(() => void this.renderizarBotonPaypal());
            }
          },
          onError: () => {
            this.errorMsg.set('Ocurrio un error con PayPal. Intenta de nuevo.');
          },
        })
        .render(contenedor);
    } catch {
      this.errorMsg.set('No se pudo cargar PayPal. Intenta de nuevo en unos segundos.');
    }
  }

  protected onArchivoSeleccionado(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.archivoComprobante.set(input.files?.[0] ?? null);
  }

  protected async enviarQr(): Promise<void> {
    const archivo = this.archivoComprobante();
    if (!archivo || !this.stockOk()) return;

    this.estado.set('procesando');
    this.errorMsg.set('');
    try {
      const formData = new FormData();
      formData.append('file', archivo);
      const ventas = await firstValueFrom(
        this.http.post<VentaCreada[]>(`${environment.apiUrl}/ventas/checkout/qr`, formData),
      );
      this.ventasCreadas.set(ventas);
      this.estado.set('listo-qr');
    } catch (err) {
      this.errorMsg.set(this.extraerError(err));
      this.estado.set('formulario');
    }
  }

  private extraerError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'No se pudo procesar el pago.';
  }

  protected irATienda(): void {
    void this.router.navigate(['/tienda-atelier-aranier']);
  }
}
