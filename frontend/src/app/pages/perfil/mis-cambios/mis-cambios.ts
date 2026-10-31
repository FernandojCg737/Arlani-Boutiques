import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  OnInit,
  afterRenderEffect,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { PaypalSdk } from '../../../services/paypal-sdk';
import { CambioPrenda, ESTADO_CAMBIO, MOTIVO_CAMBIO } from '../../admin/cambios/cambios';

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

interface CambioCliente extends CambioPrenda {
  tienda: { nombre: string; color_marca: string };
  metodos: MetodoPublico[];
  diferencia_usd: string | null;
}

interface Linea {
  item_linea_id: number;
  producto_nombre: string;
  imagen_url: string | null;
  talla_codigo: string;
  color_nombre: string;
  cantidad: number;
  disponibles: number;
  precio_pagado: string;
}

interface StockSucursal {
  sucursal_id: number;
  sucursal_nombre: string;
  stock: number;
}

interface Variante {
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  stock: number;
  sucursales: StockSucursal[];
}

interface Prenda {
  producto_id: number;
  nombre: string;
  precio: string;
  imagen_url: string | null;
  variantes: Variante[];
}

interface Opciones {
  venta_id: number;
  plazo_hasta: string;
  puede_cambiar: boolean;
  motivo_no: string | null;
  tienda_nombre: string;
  // Si la prenda nueva cuesta menos: a su PayPal o en la tienda.
  reembolso: 'paypal' | 'en_tienda';
  sucursal_id: number;
  sucursal_nombre: string;
  lineas: Linea[];
  prendas: Prenda[];
}

// CU Cambio de prendas (cliente): pedir el cambio de una prenda de una
// compra (hasta 24 h despues) por otra de la misma tienda, seguir su estado
// y pagar la diferencia si la prenda nueva cuesta mas.
@Component({
  selector: 'app-mis-cambios',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './mis-cambios.html',
  styleUrls: ['../perfil.scss', './mis-cambios.scss'],
})
export class MisCambios implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly paypalSdk = inject(PaypalSdk);
  private readonly api = `${environment.apiUrl}/cambios`;

  // En Mis Compras solo se usa el formulario (sin la lista de cambios, que
  // vive en su propia pestaña); avisa cuando se pide un cambio.
  readonly mostrarLista = input(true);
  readonly solicitado = output<void>();

  protected readonly estadoLabel = ESTADO_CAMBIO;
  protected readonly motivoLabel = MOTIVO_CAMBIO;
  protected readonly cambios = signal<CambioCliente[]>([]);
  protected readonly aviso = signal('');

  // Mis Compras lo llama al pedir una devolucion: el aviso del cambio ya no aplica.
  limpiarAviso(): void {
    this.aviso.set('');
  }

  // ------------------------------------------------ pedir un cambio
  protected readonly opciones = signal<Opciones | null>(null);
  protected readonly cargandoOpciones = signal(false);
  protected readonly lineaId = signal<number | null>(null);
  protected readonly cantidad = signal(1);
  protected readonly productoId = signal<number | null>(null);
  protected readonly tallaId = signal<number | null>(null);
  protected readonly colorId = signal<number | null>(null);
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly motivo = signal<'talla' | 'color' | 'modelo' | 'defecto' | 'otro'>('talla');
  protected readonly observaciones = signal('');
  protected readonly enviando = signal(false);
  protected readonly errorModal = signal('');

  protected readonly linea = computed(() => this.opciones()?.lineas.find((l) => l.item_linea_id === this.lineaId()) ?? null);
  protected readonly prenda = computed(() => this.opciones()?.prendas.find((p) => p.producto_id === this.productoId()) ?? null);
  // Tallas de la prenda elegida con stock, y colores de la talla elegida.
  protected readonly tallas = computed(() => {
    const vistas = new Map<number, string>();
    for (const v of this.prenda()?.variantes ?? []) vistas.set(v.talla_id, v.talla_codigo);
    return [...vistas].map(([id, codigo]) => ({ id, codigo }));
  });
  protected readonly colores = computed(() =>
    (this.prenda()?.variantes ?? []).filter((v) => v.talla_id === this.tallaId()),
  );
  protected readonly variante = computed(
    () => this.prenda()?.variantes.find((v) => v.talla_id === this.tallaId() && v.color_id === this.colorId()) ?? null,
  );
  protected readonly diferencia = computed(() => {
    const l = this.linea();
    const p = this.prenda();
    if (!l || !p) return null;
    return (Number(p.precio) - Number(l.precio_pagado)) * this.cantidad();
  });
  // Sucursal donde recoge la prenda nueva (y entrega la que devuelve).
  protected readonly sucursal = computed(
    () => this.variante()?.sucursales.find((s) => s.sucursal_id === this.sucursalId()) ?? null,
  );
  protected readonly listo = computed(() => {
    const s = this.sucursal();
    const l = this.linea();
    return !!l && !!s && s.stock >= this.cantidad() && this.cantidad() >= 1 && this.cantidad() <= l.disponibles;
  });

  // ------------------------------------------------ pagar la diferencia
  protected readonly pagando = signal<{ cambio: CambioCliente; metodo: MetodoPublico } | null>(null);
  protected readonly archivo = signal<File | null>(null);
  protected readonly procesandoPago = signal(false);
  protected readonly errorPago = signal('');
  private readonly paypalContainer = viewChild<ElementRef<HTMLDivElement>>('paypalCambio');
  private paypalPara: string | null = null;

  constructor() {
    // Despues del render, con el contenedor ya en la pagina.
    afterRenderEffect(() => {
      const contenedor = this.paypalContainer()?.nativeElement;
      const p = this.pagando();
      if (!contenedor || !p || p.metodo.tipo !== 'paypal') {
        this.paypalPara = null;
        this.desmontarPaypal?.();
        this.desmontarPaypal = null;
        return;
      }
      this.renderizarPaypal(contenedor, p.cambio, p.metodo);
    });
  }

  ngOnInit(): void {
    if (this.mostrarLista()) void this.cargar();
  }

  protected readonly cargado = signal(false);

  private async cargar(): Promise<void> {
    try {
      this.cambios.set(await firstValueFrom(this.http.get<CambioCliente[]>(`${this.api}/mios`)));
    } catch {
      this.cambios.set([]);
    } finally {
      this.cargado.set(true);
    }
  }

  // Lo llama Mis compras con el boton "Cambiar prenda".
  async abrir(ventaId: number): Promise<void> {
    this.errorModal.set('');
    this.aviso.set('');
    this.lineaId.set(null);
    this.cantidad.set(1);
    this.productoId.set(null);
    this.tallaId.set(null);
    this.colorId.set(null);
    this.sucursalId.set(null);
    this.motivo.set('talla');
    this.observaciones.set('');
    this.cargandoOpciones.set(true);
    try {
      const o = await firstValueFrom(this.http.get<Opciones>(`${this.api}/opciones/${ventaId}`));
      this.opciones.set(o);
      const unica = o.lineas.filter((l) => l.disponibles > 0);
      if (unica.length === 1) this.lineaId.set(unica[0].item_linea_id);
    } catch (err) {
      this.aviso.set(this.extraerError(err));
    } finally {
      this.cargandoOpciones.set(false);
    }
  }

  protected cerrar(): void {
    this.opciones.set(null);
  }

  protected elegirProducto(p: Prenda): void {
    this.productoId.set(p.producto_id);
    this.tallaId.set(null);
    this.colorId.set(null);
    this.sucursalId.set(null);
    const tallas = p.variantes.filter((v) => this.tallaDisponible(p, v.talla_id));
    if (new Set(tallas.map((v) => v.talla_id)).size === 1) this.elegirTalla(tallas[0].talla_id);
  }

  protected elegirTalla(id: number): void {
    this.tallaId.set(id);
    // Si en esa talla hay un solo color que se pueda elegir, queda elegido.
    const p = this.prenda();
    const opciones = (p?.variantes ?? []).filter((v) => v.talla_id === id && p && this.colorDisponible(p, v));
    if (opciones.length === 1) this.elegirColor(opciones[0]);
    else {
      this.colorId.set(null);
      this.sucursalId.set(null);
    }
  }

  protected elegirColor(v: Variante): void {
    this.colorId.set(v.color_id);
    // Se propone la sucursal de la compra si tiene stock; si no, la unica que tenga.
    const conStock = v.sucursales.filter((s) => s.stock >= this.cantidad());
    const deLaCompra = conStock.find((s) => s.sucursal_id === this.opciones()?.sucursal_id);
    this.sucursalId.set(deLaCompra?.sucursal_id ?? (conStock.length === 1 ? conStock[0].sucursal_id : null));
  }

  // Un color sirve si no es la misma prenda y alguna sucursal tiene stock.
  protected colorDisponible(p: Prenda, v: Variante): boolean {
    return !this.esLaMisma(p, v) && v.sucursales.some((s) => s.stock >= this.cantidad());
  }

  // La talla sirve si tiene algun color disponible.
  protected tallaDisponible(p: Prenda, tallaId: number): boolean {
    return p.variantes.some((v) => v.talla_id === tallaId && this.colorDisponible(p, v));
  }

  protected esLaMisma(p: Prenda, v: Variante): boolean {
    const l = this.linea();
    return !!l && p.nombre === l.producto_nombre && v.talla_codigo === l.talla_codigo && v.color_nombre === l.color_nombre;
  }

  protected async enviar(): Promise<void> {
    const o = this.opciones();
    const v = this.variante();
    if (!o || !v || !this.listo()) return;
    this.enviando.set(true);
    this.errorModal.set('');
    try {
      const nuevo = await firstValueFrom(
        this.http.post<CambioCliente>(this.api, {
          venta_id: o.venta_id,
          item_linea_id: this.lineaId(),
          cantidad: this.cantidad(),
          producto_id: this.productoId(),
          talla_id: v.talla_id,
          color_id: v.color_id,
          sucursal_id: this.sucursalId(),
          motivo: this.motivo(),
          observaciones: this.observaciones().trim() || null,
        }),
      );
      this.cambios.update((cs) => [nuevo, ...cs]);
      this.opciones.set(null);
      this.aviso.set(
        `Pedimos tu cambio #${nuevo.id} a ${o.tienda_nombre}. Te avisamos cuando lo revisen; síguelo en la pestaña Mis Cambios.`,
      );
      this.solicitado.emit();
    } catch (err) {
      this.errorModal.set(this.extraerError(err));
    } finally {
      this.enviando.set(false);
    }
  }

  protected async cancelar(c: CambioCliente): Promise<void> {
    if (!confirm(`¿Cancelar el cambio #${c.id}?`)) return;
    try {
      const nuevo = await firstValueFrom(this.http.post<CambioCliente>(`${this.api}/${c.id}/cancelar`, {}));
      this.reemplazar(nuevo);
    } catch (err) {
      this.aviso.set(this.extraerError(err));
    }
  }

  // ------------------------------------------------ pago de la diferencia
  protected elegirMetodo(c: CambioCliente, m: MetodoPublico): void {
    this.errorPago.set('');
    this.archivo.set(null);
    this.pagando.set({ cambio: c, metodo: m });
  }

  protected esMetodoActivo(c: CambioCliente, m: MetodoPublico): boolean {
    const p = this.pagando();
    return p?.cambio.id === c.id && p.metodo.id === m.id;
  }

  private desmontarPaypal: (() => void) | null = null;
  private paypalContenedor: HTMLElement | null = null;

  private renderizarPaypal(contenedor: HTMLDivElement, c: CambioCliente, m: MetodoPublico): void {
    if (!contenedor.isConnected || !m.paypal_client_id) return;
    const clave = `${c.id}:${m.id}`;
    if (this.paypalPara === clave && this.paypalContenedor === contenedor) return;
    this.paypalPara = clave;
    this.paypalContenedor = contenedor;
    this.desmontarPaypal?.();
    // Botones con el client-id de la tienda, aislados en su iframe.
    this.desmontarPaypal = this.paypalSdk.montarBotones(contenedor, m.paypal_client_id, {
      crearOrden: async () =>
        (await firstValueFrom(this.http.post<{ order_id: string }>(`${this.api}/${c.id}/paypal/orden`, {}))).order_id,
      aprobar: async (orderId: string) => {
        this.procesandoPago.set(true);
        try {
          const nuevo = await firstValueFrom(
            this.http.post<CambioCliente>(`${this.api}/${c.id}/paypal/capturar/${orderId}`, {}),
          );
          this.reemplazar(nuevo);
          this.pagando.set(null);
          this.aviso.set(`Listo: pagaste la diferencia del cambio #${c.id}. Recoge tu prenda en ${nuevo.sucursal_nombre}.`);
        } catch (err) {
          this.errorPago.set(this.extraerError(err));
        } finally {
          this.procesandoPago.set(false);
        }
      },
      cancelar: () => this.errorPago.set('Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.'),
      error: () => this.errorPago.set('Ocurrió un error con PayPal. Intenta de nuevo o elige otro método.'),
    });
  }

  protected onArchivo(event: Event): void {
    const input = event.target as HTMLInputElement;
    const f = input.files?.[0] ?? null;
    if (f && f.size > 5 * 1024 * 1024) {
      this.errorPago.set('La foto pesa más de 5 MB. Elige una más liviana.');
      input.value = '';
      return;
    }
    this.errorPago.set('');
    this.archivo.set(f);
  }

  protected async enviarComprobante(): Promise<void> {
    const p = this.pagando();
    const archivo = this.archivo();
    if (!p || !archivo) return;
    this.procesandoPago.set(true);
    this.errorPago.set('');
    try {
      const datos = new FormData();
      datos.append('metodo_pago_id', String(p.metodo.id));
      datos.append('file', archivo);
      const nuevo = await firstValueFrom(this.http.post<CambioCliente>(`${this.api}/${p.cambio.id}/comprobante`, datos));
      this.reemplazar(nuevo);
      this.pagando.set(null);
      this.aviso.set(`Recibimos tu comprobante del cambio #${p.cambio.id}. La tienda lo revisa y te avisamos.`);
    } catch (err) {
      this.errorPago.set(this.extraerError(err));
    } finally {
      this.procesandoPago.set(false);
    }
  }

  private reemplazar(nuevo: CambioCliente): void {
    this.cambios.update((cs) => cs.map((x) => (x.id === nuevo.id ? nuevo : x)));
  }

  protected numero(valor: string | number | null): number {
    return Number(valor ?? 0);
  }

  private extraerError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'No se pudo completar la acción.';
  }
}
