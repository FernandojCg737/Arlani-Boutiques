import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, effect, inject, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Auth } from '../../services/auth';
import { CatalogoClienteAuto } from '../../services/offline/catalogo-cliente-auto';
import { CatalogoCliente, ItemLocal, OfflineDb, PaypalLocal, ProductoLocal, TiendaLocal, VarianteLocal } from '../../services/offline/offline-db';
import { ImagenesOffline } from '../../services/offline/imagenes-offline';
import { Sincronizacion } from '../../services/offline/sincronizacion';
import { mensajeError } from '../../services/plataforma';
import { ESTADO_OPERACION } from '../admin/sin-conexion/sin-conexion';

interface GrupoCompra {
  sucursal_id: number;
  sucursal_nombre: string;
  empresa_nombre: string;
  tienda: TiendaLocal | null;
  items: ItemLocal[];
  total: number;
}

// Cliente con sesión sin conexión (P4): descarga el catálogo de las tiendas
// que trabajan sin conexión (CU11), lo consulta sin internet y reserva o
// compra; se guarda en el dispositivo y se envía sola al volver la conexión
// (CU12). Una compra no se cobra sin internet: al volver, la app le pide
// pagarla (en línea) o confirmarla (contra entrega), revisando precio y stock.
// Con una de sus cuentas PayPal autorizadas ve "Pago enviado" y se cobra sola
// al sincronizar, solo por las prendas que sigan con stock y al mismo precio.
// El cliente junta prendas de varias tiendas y sucursales: al confirmar se
// guarda una operación por sucursal (cada tienda recibe la suya).
@Component({
  selector: 'app-sin-conexion-cliente',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './sin-conexion-cliente.html',
  styleUrls: ['../admin/ventas/ventas.scss', '../admin/sin-conexion/sin-conexion.scss', './sin-conexion-cliente.scss'],
})
export class SinConexionCliente implements OnInit {
  private readonly auth = inject(Auth);
  protected readonly db = inject(OfflineDb);
  protected readonly auto = inject(CatalogoClienteAuto);
  protected readonly sync = inject(Sincronizacion);
  protected readonly imagenes = inject(ImagenesOffline);

  protected readonly estadoLabel = ESTADO_OPERACION;
  // Se descarga y se mantiene al día solo (catalogo-cliente-auto.ts).
  protected readonly catalogo = this.auto.catalogo;
  protected readonly tiendaId = signal<number | null>(null);
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly buscar = signal('');
  protected readonly error = signal('');
  protected readonly aviso = signal('');

  protected readonly productoSel = signal<ProductoLocal | null>(null);
  protected readonly varianteSel = signal<VarianteLocal | null>(null);
  protected readonly cantidad = signal(1);
  // Lo elegido, de cualquier tienda (se guarda en el dispositivo).
  protected readonly items = signal<ItemLocal[]>(this.leerCarrito());
  protected readonly horario = signal(this.mananaMediodia());
  protected readonly guardando = signal(false);
  protected readonly modo = signal<'reservar' | 'comprar'>('reservar');
  protected readonly entrega = signal<'retiro' | 'envio'>('retiro');
  protected readonly direccionId = signal<number | null>(null);
  // Sin conexión se paga con una cuenta PayPal autorizada (se cobra sola al
  // volver internet) o contra entrega: "en línea" no aplica aquí.
  protected readonly formaPago = signal<'contra_entrega' | 'paypal_guardado'>('paypal_guardado');
  // Sus cuentas PayPal (Métodos de pago) y la elegida para pagar.
  protected readonly paypals = computed<PaypalLocal[]>(() => this.catalogo()?.paypals ?? []);
  protected readonly paypalId = signal<number | null>(null);

  protected readonly tienda = computed<TiendaLocal | null>(
    () => this.catalogo()?.tiendas.find((t) => t.empresa_id === this.tiendaId()) ?? null,
  );

  // Lo elegido agrupado por tienda y sucursal: una operación por grupo.
  protected readonly grupos = computed<GrupoCompra[]>(() => {
    const tiendas = this.catalogo()?.tiendas ?? [];
    const grupos = new Map<number, GrupoCompra>();
    for (const i of this.items()) {
      const s = i.sucursal_id ?? 0;
      const g = grupos.get(s) ?? {
        sucursal_id: s,
        sucursal_nombre: i.sucursal_nombre ?? '',
        empresa_nombre: i.empresa_nombre ?? '',
        tienda: tiendas.find((t) => t.empresa_id === i.empresa_id) ?? null,
        items: [],
        total: 0,
      };
      g.items.push(i);
      g.total += Number(i.precio) * i.cantidad;
      grupos.set(s, g);
    }
    return [...grupos.values()];
  });

  // Formas de pago que aceptan TODAS las tiendas de lo elegido.
  private readonly tiendasElegidas = computed(() => {
    const g = this.grupos().map((x) => x.tienda);
    return g.length ? g : [this.tienda()];
  });
  protected readonly aceptaContraEntrega = computed(() => this.tiendasElegidas().every((t) => !!t?.acepta_contra_entrega));
  protected readonly aceptaPaypal = computed(() => this.tiendasElegidas().every((t) => !!t?.acepta_paypal));
  private readonly empresasElegidas = computed(() =>
    this.tiendasElegidas().map((t) => t?.empresa_id).filter((id): id is number => id !== undefined),
  );

  // La cuenta sirve si está autorizada con Arlani o en TODAS las tiendas de lo elegido.
  protected paypalSirve(pp: PaypalLocal): boolean {
    return pp.autorizada || this.empresasElegidas().every((id) => (pp.tiendas ?? []).includes(id));
  }

  // Cualquier cuenta registrada sirve: si ya tiene permiso se cobra sola; si
  // no, al volver internet se confirma el pago una vez y queda autorizada.
  protected estadoPaypal(pp: PaypalLocal): string {
    return this.paypalSirve(pp)
      ? 'se cobra sola al volver internet'
      : 'al volver internet confirmas el pago una vez y queda autorizada';
  }

  protected readonly direcciones = computed(() => this.catalogo()?.direcciones ?? []);
  protected readonly faltaParaComprar = computed(() => {
    const falta: string[] = [];
    if (!this.items().length) falta.push('Elige prendas del catálogo.');
    if (this.modo() === 'comprar' && this.entrega() === 'envio' && this.direccionId() === null) {
      falta.push(
        this.direcciones().length
          ? 'Elige la dirección de envío.'
          : 'No tienes direcciones guardadas: agrégalas en Mi cuenta con conexión.',
      );
    }
    if (this.modo() === 'reservar' && !this.horario()) falta.push('Indica hasta cuándo la recoges.');
    if (this.modo() === 'comprar' && this.items().length) {
      if (!this.aceptaPaypal() && !this.aceptaContraEntrega()) {
        falta.push('Estas tiendas no reciben pagos sin conexión (PayPal o contra entrega).');
      }
    }
    return falta;
  });

  // Prendas con stock conocido en la sucursal elegida.
  protected readonly productos = computed(() => {
    const t = this.tienda();
    const s = this.sucursalId();
    if (!t || s === null) return [];
    const q = this.buscar().trim().toLowerCase();
    return t.productos
      .map((p) => ({ ...p, variantes: p.variantes.filter((v) => v.sucursal_id === s && v.stock > 0) }))
      .filter((p) => p.variantes.length && (!q || p.nombre.toLowerCase().includes(q)));
  });

  protected readonly total = computed(() => this.items().reduce((t, i) => t + Number(i.precio) * i.cantidad, 0));

  protected readonly desactualizado = computed(() => {
    const c = this.catalogo();
    return !!c && Date.now() - new Date(c.descargado_en).getTime() > 6 * 3_600_000;
  });

  protected readonly misOperaciones = computed(() => this.sync.operaciones());

  constructor() {
    // Cada actualización automática: el catálogo nuevo, sin perder la tienda,
    // la sucursal ni las prendas que el cliente ya eligió.
    effect(() => {
      const c = this.catalogo();
      if (c) untracked(() => this.usar(c));
    });
    // Si lo elegido ya no admite la forma de pago, pasa a la otra.
    effect(() => {
      const f = this.formaPago();
      if (f === 'contra_entrega' && !this.aceptaContraEntrega()) this.formaPago.set('paypal_guardado');
      else if (f === 'paypal_guardado' && !this.aceptaPaypal() && this.aceptaContraEntrega()) this.formaPago.set('contra_entrega');
    });
    // Cuenta PayPal elegida: la que eligió o, por defecto, una que ya se cobre sola.
    effect(() => {
      const todas = this.paypals();
      const id = untracked(this.paypalId);
      if (!todas.some((p) => p.id === id)) this.paypalId.set((todas.find((p) => this.paypalSirve(p)) ?? todas[0])?.id ?? null);
    });
    effect(() => this.guardarCarrito(this.items()));
  }

  ngOnInit(): void {
    this.auto.iniciar();
  }

  private usar(c: CatalogoCliente): void {
    void this.imagenes.cargar(this.auto.urls(c));
    if (c.tiendas.some((x) => x.empresa_id === this.tiendaId())) return;
    const t = c.tiendas[0] ?? null;
    if (t) this.elegirTienda(t.empresa_id);
  }

  protected async descargar(): Promise<void> {
    this.error.set('');
    try {
      await this.auto.revisar(true);
      this.aviso.set('Catálogo actualizado: puedes verlo, reservar y comprar sin internet.');
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo descargar: necesitas conexión.'));
    }
  }

  // Cambiar de tienda o de sucursal NO borra lo ya elegido.
  protected elegirTienda(id: number): void {
    this.tiendaId.set(id);
    const t = this.catalogo()?.tiendas.find((x) => x.empresa_id === id);
    if (this.direccionId() === null) this.direccionId.set(this.catalogo()?.direcciones?.[0]?.id ?? null);
    this.elegirSucursal(t?.sucursales[0]?.id ?? null);
  }

  protected elegirSucursal(id: number | null): void {
    this.sucursalId.set(id);
    this.productoSel.set(null);
    this.varianteSel.set(null);
  }

  protected elegirProducto(p: ProductoLocal): void {
    this.productoSel.set(p);
    this.varianteSel.set(p.variantes.length === 1 ? p.variantes[0] : null);
    this.cantidad.set(1);
  }

  protected disponible(p: ProductoLocal, v: VarianteLocal): number {
    const enUso = this.items()
      .filter(
        (i) =>
          i.producto_id === p.producto_id && i.talla_id === v.talla_id && i.color_id === v.color_id && i.sucursal_id === v.sucursal_id,
      )
      .reduce((t, i) => t + i.cantidad, 0);
    return v.stock - enUso;
  }

  protected agregar(): void {
    const p = this.productoSel();
    const v = this.varianteSel();
    const cant = this.cantidad();
    const t = this.tienda();
    const s = t?.sucursales.find((x) => x.id === this.sucursalId());
    if (!p || !v || !t || !s || cant < 1 || cant > this.disponible(p, v)) return;
    this.items.update((its) => {
      const i = its.findIndex(
        (x) => x.producto_id === p.producto_id && x.talla_id === v.talla_id && x.color_id === v.color_id && x.sucursal_id === s.id,
      );
      if (i >= 0) return its.map((x, k) => (k === i ? { ...x, cantidad: x.cantidad + cant } : x));
      return [
        ...its,
        {
          producto_id: p.producto_id, talla_id: v.talla_id, color_id: v.color_id, cantidad: cant, precio: p.precio,
          producto_nombre: p.nombre, talla: v.talla_codigo, color: v.color_nombre,
          empresa_id: t.empresa_id, empresa_nombre: t.nombre, sucursal_id: s.id, sucursal_nombre: s.nombre,
        },
      ];
    });
    this.productoSel.set(null);
    this.varianteSel.set(null);
  }

  protected quitar(item: ItemLocal): void {
    this.items.update((its) => its.filter((x) => x !== item));
  }

  protected async registrar(): Promise<void> {
    const grupos = this.grupos();
    if (!grupos.length || this.faltaParaComprar().length) return;
    const compra = this.modo() === 'comprar';
    const paypal = this.paypals().find((x) => x.id === this.paypalId()) ?? null;
    const conPaypal = compra && this.formaPago() === 'paypal_guardado';
    this.guardando.set(true);
    this.error.set('');
    try {
      const u = this.auth.currentUser()!;
      // Una operación por sucursal: cada tienda recibe (y cobra) lo suyo.
      for (const g of grupos) {
        await this.sync.registrar({
          tipo: compra ? 'pedido' : 'reserva',
          empresa_nombre: g.empresa_nombre,
          sucursal_id: g.sucursal_id,
          sucursal_nombre: g.sucursal_nombre,
          cliente_id: u.id,
          cliente_nombre: u.nombre,
          factura_nombre: null,
          factura_nit: null,
          horario_atencion: compra ? null : new Date(this.horario()).toISOString(),
          entrega: compra ? this.entrega() : 'retiro',
          direccion_id: compra && this.entrega() === 'envio' ? this.direccionId() : null,
          forma_pago: compra ? this.formaPago() : null,
          metodo_pago_id: conPaypal ? (paypal?.id ?? null) : null,
          paypal_cuenta: conPaypal ? (paypal?.cuenta ?? null) : null,
          items: g.items,
          total: g.total,
        });
      }
      this.items.set([]);
      const varias = grupos.length > 1 ? ` Se enviaron ${grupos.length} pedidos: cada tienda o sucursal recibe el suyo.` : '';
      if (conPaypal && !(paypal && this.paypalSirve(paypal))) {
        this.aviso.set(
          'Pago enviado. Al volver internet te pedimos confirmar el pago con tu PayPal (solo esta vez): desde ahí tu cuenta queda autorizada y tus próximas compras sin conexión se cobran solas.' +
            varias,
        );
      } else if (conPaypal) {
        const cuenta = paypal?.cuenta ? ` ${paypal.cuenta}` : '';
        this.aviso.set(
          (this.sync.enLinea()
            ? `Pago enviado: se está cobrando con tu PayPal${cuenta}. Te avisamos el resultado.`
            : `Pago enviado. Cuando vuelvas a tener internet se cobra con tu PayPal${cuenta}, solo por las prendas que sigan disponibles y al mismo precio; lo que no, no se te cobra.`) +
            varias,
        );
      } else if (this.sync.enLinea()) {
        this.aviso.set((compra ? 'Compra enviada: revísala y págala en "Compras por pagar".' : 'Reserva enviada a la tienda.') + varias);
      } else if (compra) {
        this.aviso.set(
          'Compra guardada en tu dispositivo. Cuando vuelvas a tener internet se envía sola y te pediremos pagarla (revisando precio y stock).' +
            varias,
        );
      } else {
        this.aviso.set('Reserva guardada en tu dispositivo: se enviará sola cuando vuelvas a tener internet.' + varias);
      }
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo guardar.'));
    } finally {
      this.guardando.set(false);
    }
  }

  protected estadoDe(o: { forma_pago?: string | null; estado: string }): string {
    if (o.forma_pago === 'paypal_guardado' && o.estado === 'pagada') return 'Pago finalizado con éxito';
    return this.estadoLabel[o.estado];
  }

  protected hace(fecha: string): string {
    const min = Math.round((Date.now() - new Date(fecha).getTime()) / 60_000);
    if (min < 60) return min < 1 ? 'hace un momento' : `hace ${min} min`;
    const h = Math.round(min / 60);
    return h < 48 ? `hace ${h} h` : `hace ${Math.round(h / 24)} días`;
  }

  private get claveCarrito(): string {
    return `arlani_carrito_offline:${this.auth.currentUser()?.id ?? 0}`;
  }

  private leerCarrito(): ItemLocal[] {
    try {
      const guardado = JSON.parse(localStorage.getItem(this.claveCarrito) ?? '[]') as ItemLocal[];
      return Array.isArray(guardado) ? guardado.filter((i) => i.sucursal_id) : [];
    } catch {
      return [];
    }
  }

  private guardarCarrito(items: ItemLocal[]): void {
    try {
      localStorage.setItem(this.claveCarrito, JSON.stringify(items));
    } catch {
      // Sin almacenamiento: lo elegido vive solo mientras la página esté abierta.
    }
  }

  private mananaMediodia(): string {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T12:00`;
  }
}
