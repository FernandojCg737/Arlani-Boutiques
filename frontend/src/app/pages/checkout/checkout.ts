import { DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  OnDestroy,
  OnInit,
  afterRenderEffect,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Cart } from '../../services/cart';
import { DireccionCliente, MisDirecciones } from '../perfil/mis-direcciones/mis-direcciones';
import { PaypalSdk } from '../../services/paypal-sdk';

interface StockItem {
  detalle_id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  sucursal_nombre: string;
  cantidad_pedida: number;
  cantidad_disponible: number;
  disponible: boolean;
}

interface MetodoPublico {
  id: number;
  tipo: 'paypal' | 'qr' | 'transferencia' | 'otro';
  nombre: string;
  instrucciones: string | null;
  paypal_client_id: string | null;
  qr_url: string | null;
  banco: string | null;
  numero_cuenta: string | null;
  tipo_cuenta: string | null;
  titular: string | null;
  documento_titular: string | null;
  requiere_comprobante: boolean;
}

interface ItemTienda {
  detalle_id: number;
  producto_id: number;
  producto_nombre: string;
  imagen_url: string | null;
  talla_codigo: string;
  color_nombre: string;
  sucursal_id: number;
  sucursal_nombre: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
}

interface TiendaCheckout {
  empresa_id: number;
  nombre: string;
  subdominio: string;
  logo_url: string | null;
  color_marca: string;
  operativa: boolean;
  items: ItemTienda[];
  total: number;
  total_usd: number;
  metodos: MetodoPublico[];
  acepta_pagar_todo: boolean;
}

interface VentaCreada {
  id: number;
  sucursal_nombre: string;
  tienda: { id: number; nombre: string; color_marca: string } | null;
}

interface Pagada {
  tienda: string;
  color: string;
  ventas: VentaCreada[];
  pendiente: boolean;
  metodo: string;
}

type Estado = 'cargando' | 'listo' | 'vacio' | 'error';

// CU11 + CU21: checkout por tienda. Cada boutique cobra en SU cuenta con los
// metodos que registro: PayPal (con sus credenciales) se confirma solo; QR,
// transferencia u otro piden comprobante y quedan pendientes hasta que el
// personal de esa tienda lo apruebe. Si el carrito junta prendas de varias
// tiendas, se paga una tienda a la vez y lo demas sigue en el carrito.
//
// La sucursal de retiro de cada prenda se elige al agregarla al carrito; si
// una tienda tiene prendas en varias sucursales, su pago genera una venta
// por sucursal.
@Component({
  selector: 'app-checkout',
  imports: [RouterLink, DecimalPipe, MisDirecciones],
  templateUrl: './checkout.html',
  styleUrl: './checkout.scss',
})
export class Checkout implements OnInit, OnDestroy {
  private readonly cart = inject(Cart);
  private readonly http = inject(HttpClient);
  private readonly paypalSdk = inject(PaypalSdk);
  private readonly api = `${environment.apiUrl}/ventas/checkout`;

  private readonly paypalContainer = viewChild<ElementRef<HTMLDivElement>>('paypalContainer');

  protected readonly estado = signal<Estado>('cargando');
  protected readonly tiendas = signal<TiendaCheckout[]>([]);
  protected readonly stock = signal<StockItem[] | null>(null);
  protected readonly pagadas = signal<Pagada[]>([]);

  // Tienda y metodo que el cliente esta pagando ahora (una a la vez).
  protected readonly tiendaActiva = signal<number | null>(null);
  protected readonly metodoActivo = signal<MetodoPublico | null>(null);
  protected readonly archivo = signal<File | null>(null);
  protected readonly procesando = signal(false);
  protected readonly errorMsg = signal('');

  // Entrega: recojo en la sucursal o envio a una direccion del cliente (vale
  // para todo lo que pague en esta pantalla).
  protected readonly direcciones = signal<DireccionCliente[]>([]);
  protected readonly entrega = signal<'retiro' | 'envio'>('retiro');
  protected readonly direccionId = signal<number | null>(null);
  protected readonly entregaLista = computed(() => this.entrega() === 'retiro' || this.direccionId() !== null);
  private readonly formDireccion = viewChild(MisDirecciones);

  protected readonly sinStock = computed(() => {
    const ids = new Set<number>();
    for (const s of this.stock() ?? []) if (!s.disponible) ids.add(s.detalle_id);
    return ids;
  });
  protected readonly totalGeneral = computed(() => this.tiendas().reduce((t, x) => t + Number(x.total), 0));

  // "Pagar todo": un solo cobro con el PayPal de Arlani para todas las
  // tiendas; Arlani le envia a cada una lo suyo al instante.
  private readonly paypalTodo = viewChild<ElementRef<HTMLDivElement>>('paypalTodo');
  protected readonly modoTodo = signal(false);
  protected readonly totalUsd = computed(() =>
    this.tiendas().reduce((t, x) => t + Number(x.total_usd), 0).toFixed(2),
  );
  protected readonly tiendasSinPagarTodo = computed(() =>
    this.tiendas().filter((t) => !t.operativa || !t.acepta_pagar_todo || this.faltantes(t).length > 0),
  );
  protected readonly razonesSinPagarTodo = computed(() =>
    this.tiendasSinPagarTodo()
      .map((t) => this.razonSinPagarTodo(t))
      .join('; '),
  );
  protected readonly puedePagarTodo = computed(
    () => this.tiendas().length > 1 && this.stock() !== null && this.tiendasSinPagarTodo().length === 0,
  );

  private paypalRenderizadoPara: string | null = null;

  constructor() {
    // Los botones de PayPal se dibujan cuando aparece su contenedor (al
    // elegir PayPal en una tienda) y se vuelven a dibujar si cambia la tienda.
    // Despues del render: asi el contenedor de la tienda nueva ya esta en la
    // pagina y el de la anterior ya no.
    afterRenderEffect(() => {
      const contenedor = this.paypalContainer()?.nativeElement;
      const metodo = this.metodoActivo();
      const empresa = this.tiendaActiva();
      if (!contenedor || metodo?.tipo !== 'paypal' || empresa === null) {
        this.paypalRenderizadoPara = null;
        this.desmontarPaypal?.();
        this.desmontarPaypal = null;
        return;
      }
      this.renderizarPaypal(contenedor, empresa, metodo);
    });
  }

  ngOnInit(): void {
    void this.cargar();
    void this.cargarDirecciones();
  }

  private async cargarDirecciones(): Promise<void> {
    try {
      const ds = await firstValueFrom(this.http.get<DireccionCliente[]>(`${environment.apiUrl}/direcciones`));
      this.direcciones.set(ds);
      this.direccionId.set(ds.find((d) => d.predeterminada)?.id ?? ds[0]?.id ?? null);
    } catch {
      this.direcciones.set([]);
    }
  }

  // Cambiar la entrega cierra "Pagar todo" (sus botones se vuelven a abrir).
  protected elegirEntrega(e: 'retiro' | 'envio'): void {
    this.entrega.set(e);
    this.modoTodo.set(false);
  }

  protected agregarDireccion(): void {
    this.formDireccion()?.abrirNueva();
  }

  protected alGuardarDireccion(d: DireccionCliente): void {
    this.direcciones.update((ds) => [...ds, d]);
    this.direccionId.set(d.id);
    this.entrega.set('envio');
  }

  // direccion_id para el backend (solo con envio a domicilio).
  private envioQuery(): string {
    const id = this.entrega() === 'envio' ? this.direccionId() : null;
    return id ? `?direccion_id=${id}` : '';
  }

  ngOnDestroy(): void {
    this.desmontarPaypal?.();
  }

  private async cargar(): Promise<void> {
    try {
      const tiendas = await firstValueFrom(this.http.get<TiendaCheckout[]>(`${this.api}/tiendas`));
      this.tiendas.set(tiendas);
      if (tiendas.length === 0) {
        this.estado.set('vacio');
        return;
      }
      this.estado.set('listo');
      // Con una sola tienda y un solo metodo, queda elegido de entrada.
      const unica = tiendas.length === 1 ? tiendas[0] : null;
      if (unica && unica.operativa && unica.metodos.length === 1) this.elegir(unica, unica.metodos[0]);
      void this.verificarStock();
    } catch {
      this.estado.set('error');
    }
  }

  private async verificarStock(): Promise<void> {
    try {
      this.stock.set(await firstValueFrom(this.http.get<StockItem[]>(`${this.api}/verificar-stock`)));
    } catch {
      // La validacion definitiva la hace el backend al registrar la venta.
      this.stock.set([]);
    }
  }

  protected faltantes(t: TiendaCheckout): StockItem[] {
    const ids = new Set(t.items.map((i) => i.detalle_id));
    return (this.stock() ?? []).filter((s) => !s.disponible && ids.has(s.detalle_id));
  }

  // Por que una tienda no entra en "Pagar todo" (para decirselo al cliente).
  protected razonSinPagarTodo(t: TiendaCheckout): string {
    if (!t.operativa) return `${t.nombre} no está atendiendo por ahora`;
    if (this.faltantes(t).length > 0) return `${t.nombre} tiene prendas sin stock`;
    if (!t.metodos.some((m) => m.tipo === 'paypal')) return `${t.nombre} no recibe pagos con PayPal`;
    return `${t.nombre} todavía no registró el correo de su cuenta PayPal`;
  }

  protected sucursales(t: TiendaCheckout): string[] {
    return [...new Set(t.items.map((i) => i.sucursal_nombre))];
  }

  protected puedePagar(t: TiendaCheckout): boolean {
    return (
      t.operativa && t.metodos.length > 0 && this.stock() !== null && this.faltantes(t).length === 0 && this.entregaLista()
    );
  }

  protected async abrirPagarTodo(): Promise<void> {
    if (this.procesando()) return;
    this.errorMsg.set('');
    this.tiendaActiva.set(null);
    this.metodoActivo.set(null);
    this.modoTodo.set(true);
    await new Promise((r) => setTimeout(r));
    const contenedor = this.paypalTodo()?.nativeElement;
    if (!contenedor) return;
    contenedor.innerHTML = '';
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const paypal = (await this.paypalSdk.cargar()) as any;
      await paypal
        .Buttons({
          createOrder: async () => {
            this.errorMsg.set('');
            return (await firstValueFrom(this.http.post<{ order_id: string }>(`${this.api}/todo/paypal/orden`, {})))
              .order_id;
          },
          onApprove: async (data: { orderID: string }) => {
            this.procesando.set(true);
            try {
              const ventas = await firstValueFrom(
                this.http.post<VentaCreada[]>(`${this.api}/todo/paypal/capturar/${data.orderID}${this.envioQuery()}`, {}),
              );
              this.modoTodo.set(false);
              await this.registrarPagoTodo(ventas);
            } catch (err) {
              this.errorMsg.set(this.extraerError(err));
            } finally {
              this.procesando.set(false);
            }
          },
          onError: () => this.errorMsg.set('Ocurrió un error con PayPal. Intenta de nuevo.'),
        })
        .render(contenedor);
    } catch {
      this.errorMsg.set('No se pudo cargar PayPal. Intenta de nuevo en unos segundos.');
    }
  }

  private async registrarPagoTodo(ventas: VentaCreada[]): Promise<void> {
    const porTienda = new Map<string, Pagada>();
    for (const v of ventas) {
      const nombre = v.tienda?.nombre ?? 'Tienda';
      const p = porTienda.get(nombre) ?? {
        tienda: nombre,
        color: v.tienda?.color_marca ?? '#1f2a44',
        ventas: [],
        pendiente: false,
        metodo: 'Pagar todo (PayPal)',
      };
      p.ventas.push(v);
      porTienda.set(nombre, p);
    }
    this.pagadas.update((p) => [...p, ...porTienda.values()]);
    await this.cart.cargar();
    this.tiendas.set([]);
    this.estado.set('vacio');
  }

  protected elegir(t: TiendaCheckout, m: MetodoPublico): void {
    if (this.procesando()) return;
    this.modoTodo.set(false);
    this.errorMsg.set('');
    this.archivo.set(null);
    this.tiendaActiva.set(t.empresa_id);
    this.metodoActivo.set(m);
  }

  protected esActivo(t: TiendaCheckout, m: MetodoPublico): boolean {
    return this.tiendaActiva() === t.empresa_id && this.metodoActivo()?.id === m.id;
  }

  private desmontarPaypal: (() => void) | null = null;
  private paypalContenedor: HTMLElement | null = null;

  private renderizarPaypal(contenedor: HTMLDivElement, empresaId: number, metodo: MetodoPublico): void {
    // Al cambiar de tienda el efecto puede correr antes de que exista el
    // contenedor nuevo: se dibuja solo en uno visible y se recuerda en cual.
    if (!contenedor.isConnected || !metodo.paypal_client_id) return;
    const clave = `${empresaId}:${metodo.id}`;
    if (this.paypalRenderizadoPara === clave && this.paypalContenedor === contenedor) return;
    this.paypalRenderizadoPara = clave;
    this.paypalContenedor = contenedor;
    this.desmontarPaypal?.();
    // Botones con el client-id de ESTA tienda, aislados en su iframe.
    this.desmontarPaypal = this.paypalSdk.montarBotones(contenedor, metodo.paypal_client_id, {
      crearOrden: async () => {
        this.errorMsg.set('');
        const res = await firstValueFrom(
          this.http.post<{ order_id: string }>(`${this.api}/tienda/${empresaId}/paypal/orden`, {}),
        );
        return res.order_id;
      },
      aprobar: async (orderId: string) => {
        this.procesando.set(true);
        try {
          const ventas = await firstValueFrom(
            this.http.post<VentaCreada[]>(
              `${this.api}/tienda/${empresaId}/paypal/capturar/${orderId}${this.envioQuery()}`,
              {},
            ),
          );
          await this.registrarPago(empresaId, ventas, false, metodo.nombre);
        } catch (err) {
          this.errorMsg.set(this.extraerError(err));
        } finally {
          this.procesando.set(false);
        }
      },
      cancelar: () => this.errorMsg.set('Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.'),
      error: () => this.errorMsg.set('Ocurrió un error con PayPal. Intenta de nuevo o elige otro método.'),
    });
  }

  protected onArchivo(event: Event): void {
    const input = event.target as HTMLInputElement;
    const f = input.files?.[0] ?? null;
    if (f && f.size > 5 * 1024 * 1024) {
      this.errorMsg.set('La foto pesa más de 5 MB. Elige una más liviana.');
      input.value = '';
      return;
    }
    this.errorMsg.set('');
    this.archivo.set(f);
  }

  protected async enviarComprobante(t: TiendaCheckout): Promise<void> {
    const metodo = this.metodoActivo();
    const archivo = this.archivo();
    if (!metodo || !archivo || this.procesando()) return;
    this.procesando.set(true);
    this.errorMsg.set('');
    try {
      const datos = new FormData();
      datos.append('metodo_pago_id', String(metodo.id));
      if (this.entrega() === 'envio' && this.direccionId()) datos.append('direccion_id', String(this.direccionId()));
      datos.append('file', archivo);
      const ventas = await firstValueFrom(
        this.http.post<VentaCreada[]>(`${this.api}/tienda/${t.empresa_id}/comprobante`, datos),
      );
      await this.registrarPago(t.empresa_id, ventas, true, metodo.nombre);
    } catch (err) {
      this.errorMsg.set(this.extraerError(err));
    } finally {
      this.procesando.set(false);
    }
  }

  // Guarda el resultado, saca esa tienda de la lista y refresca el carrito
  // (lo de las demas tiendas sigue ahi para pagarlo despues).
  private async registrarPago(empresaId: number, ventas: VentaCreada[], pendiente: boolean, metodo: string): Promise<void> {
    const tienda = this.tiendas().find((t) => t.empresa_id === empresaId);
    this.pagadas.update((p) => [
      ...p,
      { tienda: tienda?.nombre ?? 'Tienda', color: tienda?.color_marca ?? '#1f2a44', ventas, pendiente, metodo },
    ]);
    this.tiendaActiva.set(null);
    this.metodoActivo.set(null);
    this.archivo.set(null);
    await this.cart.cargar();
    try {
      const tiendas = await firstValueFrom(this.http.get<TiendaCheckout[]>(`${this.api}/tiendas`));
      this.tiendas.set(tiendas);
      if (tiendas.length === 0) this.estado.set('vacio');
      void this.verificarStock();
    } catch {
      this.tiendas.set(this.tiendas().filter((t) => t.empresa_id !== empresaId));
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
}
