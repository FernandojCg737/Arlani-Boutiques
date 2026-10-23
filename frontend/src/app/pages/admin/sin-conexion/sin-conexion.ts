import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, effect, inject, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import {
  ItemLocal,
  OfflineDb,
  PaquetePersonal,
  ProductoLocal,
  VarianteLocal,
} from '../../../services/offline/offline-db';
import { DescargaAutomatica, clavePaquete } from '../../../services/offline/descarga-automatica';
import { ImagenesOffline } from '../../../services/offline/imagenes-offline';
import { Sincronizacion } from '../../../services/offline/sincronizacion';
import { mensajeError } from '../../../services/plataforma';

type Vista = 'catalogo' | 'venta' | 'reserva' | 'operaciones';

export const ESTADO_OPERACION: Record<string, string> = {
  pendiente: 'Pendiente de enviar',
  enviando: 'Enviando…',
  confirmada: 'Confirmada',
  conflicto: 'En conflicto',
  rechazada: 'Rechazada',
  resuelta: 'Resuelta por la tienda',
  anulada: 'Anulada',
  error: 'Se reintentará',
  por_pagar: 'Por pagar',
  sin_stock: 'Sin stock',
  pagada: 'Pagada',
  cancelada: 'Cancelada',
};

// Pasadas estas horas, se avisa que el stock descargado puede estar viejo.
const HORAS_DESACTUALIZADO = 6;

// Trabajar sin conexión (personal de la tienda): CU11 descargar y consultar
// el catálogo de la sucursal, CU12 registrar ventas de contado y reservas
// sin internet (se sincronizan solas) y CU13 ver esas operaciones y su estado.
@Component({
  selector: 'app-admin-sin-conexion',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './sin-conexion.html',
  styleUrls: ['../ventas/ventas.scss', './sin-conexion.scss'],
})
export class AdminSinConexion implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  protected readonly db = inject(OfflineDb);
  protected readonly sync = inject(Sincronizacion);
  protected readonly imagenes = inject(ImagenesOffline);
  protected readonly automatica = inject(DescargaAutomatica);

  protected readonly estadoLabel = ESTADO_OPERACION;
  protected readonly vista = signal<Vista>('catalogo');

  protected readonly sucursales = signal<{ id: number; nombre: string }[]>([]);
  protected readonly sucursalId = signal<number | null>(null);
  protected readonly paquete = signal<PaquetePersonal | null>(null);
  protected readonly planOffline = signal<boolean | null>(null);
  protected readonly descargando = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly buscar = signal('');

  // Formulario de venta / reserva.
  protected readonly items = signal<ItemLocal[]>([]);
  protected readonly productoSel = signal<ProductoLocal | null>(null);
  protected readonly varianteSel = signal<VarianteLocal | null>(null);
  protected readonly cantidad = signal(1);
  protected readonly clienteId = signal<number | null>(null);
  protected readonly buscarCliente = signal('');
  protected readonly facturaNombre = signal('');
  protected readonly facturaNit = signal('');
  protected readonly horario = signal(this.mananaMediodia());
  protected readonly guardando = signal(false);

  protected readonly productos = computed(() => {
    const q = this.buscar().trim().toLowerCase();
    const ps = this.paquete()?.productos ?? [];
    return q ? ps.filter((p) => p.nombre.toLowerCase().includes(q) || (p.categoria ?? '').toLowerCase().includes(q)) : ps;
  });

  protected readonly clientesFiltrados = computed(() => {
    const q = this.buscarCliente().trim().toLowerCase();
    const cs = this.paquete()?.clientes ?? [];
    return (q ? cs.filter((c) => c.nombre.toLowerCase().includes(q) || c.email.toLowerCase().includes(q)) : cs).slice(0, 8);
  });

  protected readonly total = computed(() => this.items().reduce((t, i) => t + Number(i.precio) * i.cantidad, 0));

  protected readonly horasDesdeDescarga = computed(() => {
    const p = this.paquete();
    return p ? (Date.now() - new Date(p.descargado_en).getTime()) / 3_600_000 : null;
  });
  protected readonly desactualizado = computed(() => (this.horasDesdeDescarga() ?? 0) >= HORAS_DESACTUALIZADO);

  protected readonly operacionesSucursal = computed(() => this.sync.operaciones());

  protected readonly faltaParaRegistrar = computed(() => {
    const falta: string[] = [];
    if (!this.items().length) falta.push('Agrega al menos una prenda.');
    if (this.vista() === 'reserva') {
      if (this.clienteId() === null) falta.push('Elige el cliente de la reserva.');
      if (!this.horario()) falta.push('Indica cuándo la recoge.');
    }
    return falta;
  });

  constructor() {
    // Llegó una descarga automática: se muestra el catálogo nuevo (el carrito
    // de la venta en curso no se toca).
    effect(() => {
      if (this.automatica.ultima() && this.sucursalId() !== null) untracked(() => void this.recargarPaquete());
    });
  }

  private async recargarPaquete(): Promise<void> {
    const id = this.sucursalId();
    if (id === null) return;
    const guardado = await this.db.paquete(this.clave(id));
    if (!guardado) return;
    const paquete = guardado.datos as PaquetePersonal;
    this.paquete.set(paquete);
    if (!this.sucursales().some((s) => s.id === id)) this.sucursales.update((ss) => [...ss, paquete.sucursal]);
    void this.imagenes.cargar(paquete.productos.map((p) => p.imagen_url));
  }

  async ngOnInit(): Promise<void> {
    await this.cargarSucursales();
    void this.cargarPlan();
  }

  private get usuarioId(): number {
    return this.auth.currentUser()!.id;
  }

  private clave(sucursalId: number): string {
    return clavePaquete(this.usuarioId, sucursalId);
  }

  private async cargarSucursales(): Promise<void> {
    let lista: { id: number; nombre: string }[] = [];
    if (this.sync.enLinea()) {
      try {
        lista = await firstValueFrom(
          this.http.get<{ id: number; nombre: string }[]>(`${environment.apiUrl}/ventas/presencial/sucursales`),
        );
      } catch {
        lista = [];
      }
    }
    // Sin conexión (o si el servidor no responde): las sucursales que ya se
    // descargaron en este dispositivo.
    if (!lista.length) {
      lista = (await this.db.paquetesDe(this.usuarioId))
        .filter((p) => p.clave.startsWith('personal:'))
        .map((p) => (p.datos as PaquetePersonal).sucursal);
    }
    this.sucursales.set(lista);
    // Se vuelve a la sucursal con la que se estaba trabajando.
    const recordada = Number(this.leerSucursal());
    const elegida = lista.find((s) => s.id === recordada) ?? lista[0];
    if (elegida) await this.elegirSucursal(elegida.id);
  }

  private async cargarPlan(): Promise<void> {
    if (!this.sync.enLinea()) return;
    try {
      const r = await firstValueFrom(this.http.get<{ offline: boolean }>(`${environment.apiUrl}/ventas/origenes`));
      this.planOffline.set(r.offline);
    } catch {
      this.planOffline.set(null);
    }
  }

  private leerSucursal(): string | null {
    try {
      return localStorage.getItem(`arlani_offline_sucursal_${this.usuarioId}`);
    } catch {
      return null;
    }
  }

  protected async elegirSucursal(id: number): Promise<void> {
    this.sucursalId.set(id);
    try {
      localStorage.setItem(`arlani_offline_sucursal_${this.usuarioId}`, String(id));
    } catch {
      // Sin localStorage: al recargar se elige la primera.
    }
    this.items.set([]);
    this.productoSel.set(null);
    this.varianteSel.set(null);
    const guardado = await this.db.paquete(this.clave(id));
    const paquete = (guardado?.datos as PaquetePersonal) ?? null;
    this.paquete.set(paquete);
    if (paquete) void this.imagenes.cargar(paquete.productos.map((p) => p.imagen_url));
  }

  // CU11: descarga (o actualiza) los datos de la sucursal en el dispositivo.
  protected async descargar(): Promise<void> {
    const id = this.sucursalId();
    if (id === null) return;
    this.descargando.set(true);
    this.error.set('');
    try {
      const datos = await firstValueFrom(
        this.http.get<PaquetePersonal>(`${environment.apiUrl}/offline/paquete`, { params: { sucursal_id: id } }),
      );
      await this.db.guardarPaquete({ clave: this.clave(id), usuario_id: this.usuarioId, descargado_en: datos.descargado_en, datos });
      this.paquete.set(datos);
      // Las fotos también quedan en el dispositivo, para verlas sin conexión.
      const urls = datos.productos.map((p) => p.imagen_url);
      const fotos = await this.imagenes.descargar(urls);
      await this.imagenes.cargar(urls);
      this.aviso.set(
        `Listo: ${datos.productos.length} prendas (${fotos} fotos) y ${datos.clientes.length} clientes guardados en este dispositivo.`,
      );
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo descargar: necesitas conexión.'));
    } finally {
      this.descargando.set(false);
    }
  }

  protected cambiarVista(v: Vista): void {
    this.vista.set(v);
    this.aviso.set('');
    this.error.set('');
    if (v === 'operaciones') void this.sync.cargar();
  }

  protected stockTotal(p: ProductoLocal): number {
    return p.variantes.reduce((t, v) => t + v.stock, 0);
  }

  protected elegirProducto(p: ProductoLocal): void {
    this.productoSel.set(p);
    const conStock = p.variantes.filter((v) => this.disponible(p, v) > 0);
    this.varianteSel.set(conStock.length === 1 ? conStock[0] : null);
    this.cantidad.set(1);
  }

  // Stock conocido menos lo que ya está en esta venta.
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
          producto_id: p.producto_id,
          talla_id: v.talla_id,
          color_id: v.color_id,
          cantidad: cant,
          precio: p.precio,
          producto_nombre: p.nombre,
          talla: v.talla_codigo,
          color: v.color_nombre,
        },
      ];
    });
    this.productoSel.set(null);
    this.varianteSel.set(null);
  }

  protected quitar(i: number): void {
    this.items.update((its) => its.filter((_, k) => k !== i));
  }

  // CU12: guarda la operación en el dispositivo (se envía sola con conexión).
  protected async registrar(): Promise<void> {
    const p = this.paquete();
    if (!p || this.faltaParaRegistrar().length) return;
    const tipo = this.vista() === 'reserva' ? 'reserva' : 'venta';
    const cliente = p.clientes.find((c) => c.id === this.clienteId()) ?? null;
    this.guardando.set(true);
    try {
      await this.sync.registrar({
        tipo,
        empresa_nombre: p.empresa_nombre,
        sucursal_id: p.sucursal.id,
        sucursal_nombre: p.sucursal.nombre,
        cliente_id: cliente?.id ?? null,
        cliente_nombre: cliente?.nombre ?? (this.facturaNombre().trim() || null),
        factura_nombre: tipo === 'venta' && !cliente ? this.facturaNombre().trim() || null : null,
        factura_nit: tipo === 'venta' ? this.facturaNit().trim() || null : null,
        horario_atencion: tipo === 'reserva' ? new Date(this.horario()).toISOString() : null,
        items: this.items(),
        total: this.total(),
      });
      // El stock conocido baja en el dispositivo para no vender dos veces lo mismo.
      const vendido = this.items();
      const actualizado: PaquetePersonal = {
        ...p,
        productos: p.productos.map((prod) => ({
          ...prod,
          variantes: prod.variantes.map((v) => {
            const it = vendido.find((i) => i.producto_id === prod.producto_id && i.talla_id === v.talla_id && i.color_id === v.color_id);
            return it ? { ...v, stock: Math.max(0, v.stock - it.cantidad) } : v;
          }),
        })),
      };
      await this.db.guardarPaquete({ clave: this.clave(p.sucursal.id), usuario_id: this.usuarioId, descargado_en: p.descargado_en, datos: actualizado });
      this.paquete.set(actualizado);
      this.aviso.set(
        this.sync.enLinea()
          ? `${tipo === 'venta' ? 'Venta' : 'Reserva'} registrada: se está enviando al servidor.`
          : `${tipo === 'venta' ? 'Venta' : 'Reserva'} guardada en este dispositivo. Se enviará sola cuando vuelva la conexión.`,
      );
      this.items.set([]);
      this.clienteId.set(null);
      this.buscarCliente.set('');
      this.facturaNombre.set('');
      this.facturaNit.set('');
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo guardar la operación.'));
    } finally {
      this.guardando.set(false);
    }
  }

  protected elegirCliente(c: { id: number; nombre: string }): void {
    this.clienteId.set(c.id);
    this.buscarCliente.set(c.nombre);
  }

  protected quitarCliente(): void {
    this.clienteId.set(null);
    this.buscarCliente.set('');
  }

  protected hace(fecha: string): string {
    const min = Math.round((Date.now() - new Date(fecha).getTime()) / 60_000);
    if (min < 1) return 'hace un momento';
    if (min < 60) return `hace ${min} min`;
    const h = Math.round(min / 60);
    if (h < 48) return `hace ${h} h`;
    return `hace ${Math.round(h / 24)} días`;
  }

  private mananaMediodia(): string {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(12, 0, 0, 0);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T12:00`;
  }
}
