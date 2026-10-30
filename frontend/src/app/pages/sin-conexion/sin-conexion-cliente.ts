import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Auth } from '../../services/auth';
import { CatalogoCliente, ItemLocal, OfflineDb, ProductoLocal, TiendaLocal, VarianteLocal } from '../../services/offline/offline-db';
import { ImagenesOffline } from '../../services/offline/imagenes-offline';
import { Sincronizacion } from '../../services/offline/sincronizacion';
import { mensajeError } from '../../services/plataforma';
import { ESTADO_OPERACION } from '../admin/sin-conexion/sin-conexion';

// Cliente con sesión sin conexión (P4): descarga el catálogo de las tiendas
// que trabajan sin conexión (CU11), lo consulta sin internet y reserva o
// compra; se guarda en el dispositivo y se envía sola al volver la conexión
// (CU12). Una compra no se cobra sin internet: al volver, la app le pide
// pagarla (en línea) o confirmarla (contra entrega), revisando precio y stock.
// Con su PayPal guardado ve "Pago enviado" y se cobra sola al sincronizar,
// solo por las prendas que sigan con stock y al mismo precio (o menor).
@Component({
  selector: 'app-sin-conexion-cliente',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './sin-conexion-cliente.html',
  styleUrls: ['../admin/ventas/ventas.scss', '../admin/sin-conexion/sin-conexion.scss', './sin-conexion-cliente.scss'],
})
export class SinConexionCliente implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  protected readonly db = inject(OfflineDb);
  protected readonly sync = inject(Sincronizacion);
  protected readonly imagenes = inject(ImagenesOffline);

  protected readonly estadoLabel = ESTADO_OPERACION;
  protected readonly catalogo = signal<CatalogoCliente | null>(null);
  protected readonly tiendaId = signal<number | null>(null);
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly buscar = signal('');
  protected readonly descargando = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');

  protected readonly productoSel = signal<ProductoLocal | null>(null);
  protected readonly varianteSel = signal<VarianteLocal | null>(null);
  protected readonly cantidad = signal(1);
  protected readonly items = signal<ItemLocal[]>([]);
  protected readonly horario = signal(this.mananaMediodia());
  protected readonly guardando = signal(false);
  protected readonly modo = signal<'reservar' | 'comprar'>('reservar');
  protected readonly entrega = signal<'retiro' | 'envio'>('retiro');
  protected readonly direccionId = signal<number | null>(null);
  protected readonly formaPago = signal<'en_linea' | 'contra_entrega' | 'paypal_guardado'>('en_linea');
  // Correo del PayPal guardado (null: no lo vinculó).
  protected readonly paypalGuardado = computed(() => this.catalogo()?.paypal_guardado ?? null);

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
    return falta;
  });

  protected readonly tienda = computed<TiendaLocal | null>(
    () => this.catalogo()?.tiendas.find((t) => t.empresa_id === this.tiendaId()) ?? null,
  );

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

  async ngOnInit(): Promise<void> {
    const guardado = await this.db.paquete(this.clave);
    if (guardado) this.usar(guardado.datos as CatalogoCliente);
  }

  private get clave(): string {
    return `cliente:${this.auth.currentUser()!.id}`;
  }

  private urls(c: CatalogoCliente): (string | null)[] {
    return c.tiendas.flatMap((t) => t.productos.map((p) => p.imagen_url));
  }

  private usar(c: CatalogoCliente): void {
    this.catalogo.set(c);
    void this.imagenes.cargar(this.urls(c));
    const t = c.tiendas.find((x) => x.empresa_id === this.tiendaId()) ?? c.tiendas[0] ?? null;
    if (t) this.elegirTienda(t.empresa_id);
  }

  protected async descargar(): Promise<void> {
    this.descargando.set(true);
    this.error.set('');
    try {
      const c = await firstValueFrom(this.http.get<CatalogoCliente>(`${environment.apiUrl}/offline/catalogo-cliente`));
      await this.db.guardarPaquete({ clave: this.clave, usuario_id: this.auth.currentUser()!.id, descargado_en: c.descargado_en, datos: c });
      const fotos = await this.imagenes.descargar(this.urls(c));
      this.usar(c);
      this.aviso.set(`Catálogo guardado en este dispositivo (con ${fotos} fotos): puedes verlo, reservar y comprar sin internet.`);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo descargar: necesitas conexión.'));
    } finally {
      this.descargando.set(false);
    }
  }

  protected elegirTienda(id: number): void {
    this.tiendaId.set(id);
    const t = this.catalogo()?.tiendas.find((x) => x.empresa_id === id);
    if (!t?.acepta_contra_entrega && this.formaPago() === 'contra_entrega') this.formaPago.set('en_linea');
    if (!t?.acepta_paypal && this.formaPago() === 'paypal_guardado') this.formaPago.set('en_linea');
    this.direccionId.set(this.catalogo()?.direcciones?.[0]?.id ?? null);
    this.elegirSucursal(t?.sucursales[0]?.id ?? null);
  }

  protected elegirSucursal(id: number | null): void {
    this.sucursalId.set(id);
    this.items.set([]);
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
      .filter((i) => i.producto_id === p.producto_id && i.talla_id === v.talla_id && i.color_id === v.color_id)
      .reduce((t, i) => t + i.cantidad, 0);
    return v.stock - enUso;
  }

  protected agregar(): void {
    const p = this.productoSel();
    const v = this.varianteSel();
    const cant = this.cantidad();
    if (!p || !v || cant < 1 || cant > this.disponible(p, v)) return;
    this.items.update((its) => {
      const i = its.findIndex((x) => x.producto_id === p.producto_id && x.talla_id === v.talla_id && x.color_id === v.color_id);
      if (i >= 0) return its.map((x, k) => (k === i ? { ...x, cantidad: x.cantidad + cant } : x));
      return [
        ...its,
        {
          producto_id: p.producto_id, talla_id: v.talla_id, color_id: v.color_id, cantidad: cant, precio: p.precio,
          producto_nombre: p.nombre, talla: v.talla_codigo, color: v.color_nombre,
        },
      ];
    });
    this.productoSel.set(null);
    this.varianteSel.set(null);
  }

  protected quitar(i: number): void {
    this.items.update((its) => its.filter((_, k) => k !== i));
  }

  protected async registrar(): Promise<void> {
    const t = this.tienda();
    const s = t?.sucursales.find((x) => x.id === this.sucursalId());
    if (!t || !s || this.faltaParaComprar().length) return;
    const compra = this.modo() === 'comprar';
    this.guardando.set(true);
    this.error.set('');
    try {
      const u = this.auth.currentUser()!;
      await this.sync.registrar({
        tipo: compra ? 'pedido' : 'reserva',
        empresa_nombre: t.nombre,
        sucursal_id: s.id,
        sucursal_nombre: s.nombre,
        cliente_id: u.id,
        cliente_nombre: u.nombre,
        factura_nombre: null,
        factura_nit: null,
        horario_atencion: compra ? null : new Date(this.horario()).toISOString(),
        entrega: compra ? this.entrega() : 'retiro',
        direccion_id: compra && this.entrega() === 'envio' ? this.direccionId() : null,
        forma_pago: compra ? this.formaPago() : null,
        items: this.items(),
        total: this.total(),
      });
      this.items.set([]);
      if (compra && this.formaPago() === 'paypal_guardado') {
        this.aviso.set(
          this.sync.enLinea()
            ? 'Pago enviado: se está cobrando con tu PayPal guardado. Te avisamos el resultado.'
            : 'Pago enviado. Cuando vuelvas a tener internet se cobra con tu PayPal guardado, solo por las prendas que sigan disponibles y al mismo precio; lo que no, no se te cobra.',
        );
      } else if (this.sync.enLinea()) {
        this.aviso.set(compra ? 'Compra enviada: revísala y págala en "Compras por pagar".' : 'Reserva enviada a la tienda.');
      } else if (compra) {
        this.aviso.set(
          'Compra guardada en tu dispositivo. Cuando vuelvas a tener internet se envía sola y te pediremos pagarla (revisando precio y stock).',
        );
      } else {
        this.aviso.set('Reserva guardada en tu dispositivo: se enviará sola cuando vuelvas a tener internet.');
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

  private mananaMediodia(): string {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T12:00`;
  }
}
