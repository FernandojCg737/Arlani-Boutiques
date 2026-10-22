import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { CatalogoPublico } from '../../../services/catalogo-publico';

interface DetalleVentaItem {
  id: number;
  producto_id: number;
  producto_nombre: string;
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  cantidad: number;
  precio_unitario: string;
}

interface VentaItem {
  id: number;
  tipo: string;
  sucursal_id: number;
  sucursal_nombre: string;
  fecha: string;
  total: string;
  estado: string;
  metodo_pago: string;
  estado_pago: string;
  cliente_nombre: string;
  cliente_email: string;
  atendido_por_nombre: string | null;
  comprobante_url: string | null;
  detalles: DetalleVentaItem[];
  tiene_devolucion: boolean;
  estado_devolucion: string | null;
  monto_devolucion: string | null;
}

interface VentaPage {
  items: VentaItem[];
  total: number;
  page: number;
  page_size: number;
}

interface Sucursal {
  id: number;
  nombre: string;
}

interface ClienteBusqueda {
  id: number;
  nombre: string;
  email: string;
}

interface DisponibilidadItem {
  sucursal_id: number;
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  cantidad: number;
}

interface ItemNuevaVenta {
  producto_id: number;
  producto_nombre: string;
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  cantidad: number;
  precio_unitario: number;
}

interface DetalleReservaItem {
  id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad: number;
}

interface ReservaItem {
  id: number;
  cliente_nombre: string;
  cliente_email: string;
  sucursal_nombre: string;
  horario_atencion: string;
  estado: string;
  detalles: DetalleReservaItem[];
}

interface ReservaPage {
  items: ReservaItem[];
}

interface DetalleDevolucionItem {
  id: number;
  item_linea_id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad_devuelta: number;
  precio_unitario: string;
}

interface DevolucionItem {
  id: number;
  venta_id: number;
  empleado_nombre: string;
  motivo: string;
  tipo: string;
  monto_reembolso: string;
  metodo_reembolso: string;
  estado: string;
  fecha_solicitud: string;
  fecha_resolucion: string | null;
  observaciones: string | null;
  detalles: DetalleDevolucionItem[];
  cliente_nombre: string;
  cliente_email: string;
  venta_total: string;
  venta_fecha: string;
  sucursal_nombre: string;
}

interface ItemDevolucionSeleccion {
  item_linea_id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad_comprada: number;
  cantidad_devuelta: number;
  precio_unitario: number;
  seleccionado: boolean;
}

type Vista = 'ventas' | 'reservas' | 'devoluciones';

// CU11: panel financiero de staff (Administrador, Encargado de Sucursal,
// Cajero) -- reune ventas en linea (PayPal), por QR (con aprobacion manual)
// y de mostrador en un solo lugar, y permite registrar una venta presencial
// en efectivo.
@Component({
  selector: 'app-admin-ventas',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './ventas.html',
  styleUrl: './ventas.scss',
})
export class AdminVentas implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly catalogo = inject(CatalogoPublico);

  protected readonly items = signal<VentaItem[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 20;
  protected readonly filtroTipo = signal('');
  protected readonly filtroEstadoPago = signal('');
  protected readonly filtroSucursal = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly procesando = signal<number | null>(null);

  protected readonly sucursales = signal<Sucursal[]>([]);

  protected get totalPages(): number {
    return Math.max(1, Math.ceil(this.total() / this.pageSize));
  }

  // ---------- Reservas pendientes de cobro ----------
  // CU11 tambien deja completar el pago de una reserva (CU10) cuando el
  // cliente llega a la sucursal a pagar en efectivo -- se atiende igual que
  // desde el panel de Reservas, pero sin salir de "Gestion de Ventas".
  protected readonly vista = signal<Vista>('ventas');
  protected readonly reservas = signal<ReservaItem[]>([]);
  protected readonly cargandoReservas = signal(false);

  // ---------- Devoluciones ----------
  protected readonly devoluciones = signal<DevolucionItem[]>([]);
  protected readonly cargandoDevoluciones = signal(false);
  protected readonly devolucionFormAbierto = signal(false);
  protected readonly devolucionVenta = signal<VentaItem | null>(null);
  protected readonly devolucionItems = signal<ItemDevolucionSeleccion[]>([]);
  protected readonly devolucionMotivo = signal('defecto');
  protected readonly devolucionTipo = signal('total');
  protected readonly devolucionMetodo = signal('mismo_medio');
  protected readonly devolucionObs = signal('');
  protected readonly guardandoDevolucion = signal(false);
  protected readonly errorDevolucion = signal('');
  protected readonly filtroEstadoDevolucion = signal('');
  protected readonly devolucionVerModal = signal<DevolucionItem | null>(null);

  protected readonly totalDevolucion = computed(() =>
    this.devolucionItems()
      .filter((i) => i.seleccionado)
      .reduce((sum, i) => sum + i.precio_unitario * i.cantidad_devuelta, 0),
  );

  protected cambiarVista(v: Vista): void {
    this.vista.set(v);
    if (v === 'reservas' && this.reservas().length === 0) void this.cargarReservas();
    if (v === 'devoluciones') void this.cargarDevoluciones();
  }

  private async cargarReservas(): Promise<void> {
    this.cargandoReservas.set(true);
    try {
      const [pendientes, confirmadas] = await Promise.all([
        firstValueFrom(
          this.http.get<ReservaPage>(`${environment.apiUrl}/reservas`, { params: { estado: 'pendiente', page_size: '50' } }),
        ),
        firstValueFrom(
          this.http.get<ReservaPage>(`${environment.apiUrl}/reservas`, { params: { estado: 'confirmada', page_size: '50' } }),
        ),
      ]);
      this.reservas.set([...pendientes.items, ...confirmadas.items]);
    } catch {
      this.reservas.set([]);
    } finally {
      this.cargandoReservas.set(false);
    }
  }

  protected async cobrarReserva(r: ReservaItem): Promise<void> {
    if (!confirm(`Cobrar en efectivo la reserva #${r.id} de ${r.cliente_nombre}?`)) return;
    this.procesando.set(r.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/reservas/${r.id}/completar`, {}));
      await this.cargarReservas();
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  // ---------- Nueva venta presencial / Editar venta ----------
  // El mismo formulario (armador de items por producto/talla/color) sirve
  // para crear una venta presencial nueva y para editar una existente --
  // "editando" distingue el modo; si esta seteado, confirmarVenta() manda
  // un PUT en vez de un POST y no pide cliente (no es editable).
  protected readonly formularioAbierto = signal(false);
  protected readonly editando = signal<VentaItem | null>(null);
  protected readonly clienteBusqueda = signal('');
  protected readonly clienteResultados = signal<ClienteBusqueda[]>([]);
  protected readonly clienteSeleccionado = signal<ClienteBusqueda | null>(null);
  protected readonly sucursalNuevaId = signal<number | null>(null);
  protected readonly metodoPagoEdit = signal('efectivo');
  protected readonly estadoPagoEdit = signal('completado');
  protected readonly productoBusqueda = signal('');
  protected readonly varianteSeleccionada = signal('');
  protected readonly variantesDisponibles = signal<DisponibilidadItem[]>([]);
  protected readonly productoParaVariantes = signal<{ id: number; nombre: string; precio: number } | null>(null);
  protected readonly cantidadNueva = signal(1);
  protected readonly itemsNuevaVenta = signal<ItemNuevaVenta[]>([]);
  protected readonly guardandoVenta = signal(false);
  protected readonly errorNuevaVenta = signal('');

  protected readonly productosSugeridos = computed(() => {
    const termino = this.productoBusqueda().trim().toLowerCase();
    if (!termino) return [];
    return this.catalogo
      .products()
      .filter((p) => p.name.toLowerCase().includes(termino))
      .slice(0, 8);
  });

  protected readonly totalNuevaVenta = computed(() =>
    this.itemsNuevaVenta().reduce((sum, i) => sum + i.precio_unitario * i.cantidad, 0),
  );

  ngOnInit(): void {
    // El backend ya manda solo los productos de la empresa del personal.
    this.catalogo.tienda.set(null);
    this.catalogo.load();
    this.cargarSucursales();
    this.load();
  }

  private async cargarSucursales(): Promise<void> {
    try {
      const res = await firstValueFrom(this.http.get<Sucursal[]>(`${environment.apiUrl}/sucursales/publico`));
      this.sucursales.set(res);
    } catch {
      this.sucursales.set([]);
    }
  }

  protected filtrar(): void {
    this.page.set(1);
    this.load();
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.totalPages) return;
    this.page.set(page);
    this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = {
        page: String(this.page()),
        page_size: String(this.pageSize),
      };
      if (this.filtroTipo()) params['tipo'] = this.filtroTipo();
      if (this.filtroEstadoPago()) params['estado_pago'] = this.filtroEstadoPago();
      if (this.filtroSucursal()) params['sucursal_id'] = this.filtroSucursal();

      const res = await firstValueFrom(this.http.get<VentaPage>(`${environment.apiUrl}/ventas`, { params }));
      this.items.set(res.items);
      this.total.set(res.total);
    } catch {
      this.error.set('No se pudo cargar las ventas.');
    } finally {
      this.loading.set(false);
    }
  }

  protected async aprobarQr(venta: VentaItem): Promise<void> {
    if (!confirm(`Aprobar el pago QR de la venta #${venta.id}? Esto descuenta el stock.`)) return;
    this.procesando.set(venta.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/ventas/${venta.id}/aprobar-qr`, {}));
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  protected async rechazarQr(venta: VentaItem): Promise<void> {
    if (!confirm(`Rechazar el pago QR de la venta #${venta.id}?`)) return;
    this.procesando.set(venta.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/ventas/${venta.id}/rechazar-qr`, {}));
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  // ---------- Nueva venta presencial ----------

  protected abrirFormulario(): void {
    this.formularioAbierto.set(true);
    this.editando.set(null);
    this.clienteBusqueda.set('');
    this.clienteResultados.set([]);
    this.clienteSeleccionado.set(null);
    this.sucursalNuevaId.set(this.sucursales()[0]?.id ?? null);
    this.metodoPagoEdit.set('efectivo');
    this.estadoPagoEdit.set('completado');
    this.itemsNuevaVenta.set([]);
    this.errorNuevaVenta.set('');
    this.limpiarSeleccionProducto();
  }

  // ---------- Editar venta existente ----------

  protected abrirEditar(venta: VentaItem): void {
    this.formularioAbierto.set(true);
    this.editando.set(venta);
    this.sucursalNuevaId.set(venta.sucursal_id);
    this.metodoPagoEdit.set(venta.metodo_pago);
    this.estadoPagoEdit.set(venta.estado_pago === 'pendiente' ? 'completado' : venta.estado_pago);
    this.itemsNuevaVenta.set(
      venta.detalles.map((d) => ({
        producto_id: d.producto_id,
        producto_nombre: d.producto_nombre,
        talla_id: d.talla_id,
        talla_codigo: d.talla_codigo,
        color_id: d.color_id,
        color_nombre: d.color_nombre,
        cantidad: d.cantidad,
        precio_unitario: Number(d.precio_unitario),
      })),
    );
    this.errorNuevaVenta.set('');
    this.limpiarSeleccionProducto();
  }

  protected async eliminarVenta(venta: VentaItem): Promise<void> {
    if (!confirm(`Eliminar por completo la venta #${venta.id} de ${venta.cliente_nombre}? Esto no se puede deshacer.`))
      return;
    this.procesando.set(venta.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.delete(`${environment.apiUrl}/ventas/${venta.id}`));
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  protected cerrarFormulario(): void {
    this.formularioAbierto.set(false);
    this.editando.set(null);
  }

  protected async buscarClientes(): Promise<void> {
    const termino = this.clienteBusqueda().trim();
    if (termino.length < 2) {
      this.clienteResultados.set([]);
      return;
    }
    try {
      const res = await firstValueFrom(
        this.http.get<ClienteBusqueda[]>(`${environment.apiUrl}/ventas/clientes/buscar`, {
          params: { buscar: termino },
        }),
      );
      this.clienteResultados.set(res);
    } catch {
      this.clienteResultados.set([]);
    }
  }

  protected seleccionarCliente(c: ClienteBusqueda): void {
    this.clienteSeleccionado.set(c);
    this.clienteResultados.set([]);
    this.clienteBusqueda.set(c.nombre);
  }

  private limpiarSeleccionProducto(): void {
    this.productoBusqueda.set('');
    this.productoParaVariantes.set(null);
    this.variantesDisponibles.set([]);
    this.varianteSeleccionada.set('');
    this.cantidadNueva.set(1);
  }

  protected async seleccionarProducto(p: { id: string; name: string; price: number }): Promise<void> {
    const sucursalId = this.sucursalNuevaId();
    this.productoBusqueda.set(p.name);
    this.productoParaVariantes.set({ id: Number(p.id), nombre: p.name, precio: p.price });
    this.variantesDisponibles.set([]);
    this.varianteSeleccionada.set('');

    try {
      const res = await firstValueFrom(
        this.http.get<DisponibilidadItem[]>(`${environment.apiUrl}/reservas/disponibilidad/${p.id}`),
      );
      const filtradas = sucursalId ? res.filter((v) => v.sucursal_id === sucursalId) : res;
      this.variantesDisponibles.set(filtradas);
      if (filtradas[0]) this.varianteSeleccionada.set(`${filtradas[0].talla_id}-${filtradas[0].color_id}`);
    } catch {
      this.variantesDisponibles.set([]);
    }
  }

  protected agregarItem(): void {
    const producto = this.productoParaVariantes();
    const clave = this.varianteSeleccionada();
    const variante = this.variantesDisponibles().find((v) => `${v.talla_id}-${v.color_id}` === clave);
    if (!producto || !variante) return;

    this.itemsNuevaVenta.update((items) => [
      ...items,
      {
        producto_id: producto.id,
        producto_nombre: producto.nombre,
        talla_id: variante.talla_id,
        talla_codigo: variante.talla_codigo,
        color_id: variante.color_id,
        color_nombre: variante.color_nombre,
        cantidad: this.cantidadNueva(),
        precio_unitario: producto.precio,
      },
    ]);
    this.limpiarSeleccionProducto();
  }

  protected quitarItem(index: number): void {
    this.itemsNuevaVenta.update((items) => items.filter((_, i) => i !== index));
  }

  protected async confirmarVenta(): Promise<void> {
    const sucursalId = this.sucursalNuevaId();
    const items = this.itemsNuevaVenta();
    const edit = this.editando();
    if (!sucursalId || items.length === 0) return;
    if (!edit && !this.clienteSeleccionado()) return;

    const itemsPayload = items.map((i) => ({
      producto_id: i.producto_id,
      talla_id: i.talla_id,
      color_id: i.color_id,
      cantidad: i.cantidad,
    }));

    this.guardandoVenta.set(true);
    this.errorNuevaVenta.set('');
    try {
      if (edit) {
        await firstValueFrom(
          this.http.put(`${environment.apiUrl}/ventas/${edit.id}`, {
            sucursal_id: sucursalId,
            items: itemsPayload,
            metodo_pago: this.metodoPagoEdit(),
            estado_pago: this.estadoPagoEdit(),
          }),
        );
      } else {
        await firstValueFrom(
          this.http.post(`${environment.apiUrl}/ventas/presencial`, {
            cliente_id: this.clienteSeleccionado()!.id,
            sucursal_id: sucursalId,
            items: itemsPayload,
          }),
        );
      }
      this.formularioAbierto.set(false);
      this.editando.set(null);
      await this.load();
    } catch (err) {
      this.errorNuevaVenta.set(this.extraerError(err));
    } finally {
      this.guardandoVenta.set(false);
    }
  }

  // ---------- Devoluciones (CU11) ----------

  private async cargarDevoluciones(): Promise<void> {
    this.cargandoDevoluciones.set(true);
    try {
      const params: Record<string, string> = {};
      if (this.filtroEstadoDevolucion()) params['estado'] = this.filtroEstadoDevolucion();
      const res = await firstValueFrom(
        this.http.get<DevolucionItem[]>(`${environment.apiUrl}/devoluciones`, { params }),
      );
      this.devoluciones.set(res);
    } catch {
      this.devoluciones.set([]);
    } finally {
      this.cargandoDevoluciones.set(false);
    }
  }

  protected filtrarDevoluciones(): void {
    void this.cargarDevoluciones();
  }

  protected abrirDevolucionForm(venta: VentaItem): void {
    this.devolucionVenta.set(venta);
    this.devolucionItems.set(
      venta.detalles.map((d) => ({
        item_linea_id: d.id,
        producto_nombre: d.producto_nombre,
        talla_codigo: d.talla_codigo,
        color_nombre: d.color_nombre,
        cantidad_comprada: d.cantidad,
        cantidad_devuelta: d.cantidad,
        precio_unitario: Number(d.precio_unitario),
        seleccionado: true,
      })),
    );
    this.devolucionMotivo.set('defecto');
    this.devolucionTipo.set('total');
    this.devolucionMetodo.set('mismo_medio');
    this.devolucionObs.set('');
    this.errorDevolucion.set('');
    this.devolucionFormAbierto.set(true);
  }

  protected cerrarDevolucionForm(): void {
    this.devolucionFormAbierto.set(false);
    this.devolucionVenta.set(null);
  }

  protected onDevolucionTipoChange(tipo: string): void {
    this.devolucionTipo.set(tipo);
    if (tipo === 'total') {
      this.devolucionItems.update((items) =>
        items.map((i) => ({ ...i, seleccionado: true, cantidad_devuelta: i.cantidad_comprada })),
      );
    }
  }

  protected toggleDevolucionItem(index: number): void {
    this.devolucionItems.update((items) =>
      items.map((i, idx) => (idx === index ? { ...i, seleccionado: !i.seleccionado } : i)),
    );
  }

  protected actualizarCantidadDevolucion(index: number, cantidad: number): void {
    this.devolucionItems.update((items) =>
      items.map((i, idx) =>
        idx === index ? { ...i, cantidad_devuelta: Math.min(Math.max(1, cantidad), i.cantidad_comprada) } : i,
      ),
    );
  }

  protected async confirmarDevolucion(): Promise<void> {
    const venta = this.devolucionVenta();
    if (!venta) return;

    const itemsSeleccionados = this.devolucionItems().filter((i) => i.seleccionado);
    if (itemsSeleccionados.length === 0) return;

    this.guardandoDevolucion.set(true);
    this.errorDevolucion.set('');
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/devoluciones/${venta.id}`, {
          motivo: this.devolucionMotivo(),
          tipo: this.devolucionTipo(),
          metodo_reembolso: this.devolucionMetodo(),
          observaciones: this.devolucionObs() || null,
          items: itemsSeleccionados.map((i) => ({
            item_linea_id: i.item_linea_id,
            cantidad_devuelta: i.cantidad_devuelta,
          })),
        }),
      );
      this.devolucionFormAbierto.set(false);
      await this.load();
      this.vista.set('devoluciones');
      await this.cargarDevoluciones();
    } catch (err) {
      this.errorDevolucion.set(this.extraerError(err));
    } finally {
      this.guardandoDevolucion.set(false);
    }
  }

  protected async completarDevolucion(dev: DevolucionItem): Promise<void> {
    if (!confirm(`Completar la devolucion #${dev.id}? Esto reingresa el stock y reembolsa ${dev.monto_reembolso} Bs.`))
      return;
    this.procesando.set(dev.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/devoluciones/${dev.id}/completar`, {}));
      await this.cargarDevoluciones();
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  protected async rechazarDevolucion(dev: DevolucionItem): Promise<void> {
    if (!confirm(`Rechazar la devolucion #${dev.id}?`)) return;
    this.procesando.set(dev.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/devoluciones/${dev.id}/rechazar`, {}));
      await this.cargarDevoluciones();
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  protected verDevolucion(dev: DevolucionItem): void {
    this.devolucionVerModal.set(dev);
  }

  protected cerrarVerDevolucion(): void {
    this.devolucionVerModal.set(null);
  }

  protected async eliminarDevolucion(dev: DevolucionItem): Promise<void> {
    const aviso =
      dev.estado === 'completada'
        ? `¿Estás seguro de ELIMINAR la devolución #${dev.id}?\n\nADVERTENCIA: Esta devolución ya fue completada. Al eliminarla, se revertirá el reingreso de stock en inventario y la venta #${dev.venta_id} volverá a estar 'pagada'.`
        : `¿Estás seguro de eliminar el registro de devolución #${dev.id}?`;
    if (!confirm(aviso)) return;

    this.procesando.set(dev.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.delete(`${environment.apiUrl}/devoluciones/${dev.id}`));
      if (this.devolucionVerModal()?.id === dev.id) {
        this.cerrarVerDevolucion();
      }
      await this.cargarDevoluciones();
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  protected readonly motivoLabels: Record<string, string> = {
    defecto: 'Producto defectuoso',
    talla_incorrecta: 'Talla incorrecta',
    insatisfaccion: 'Insatisfaccion',
    otro: 'Otro',
  };

  protected readonly metodoLabels: Record<string, string> = {
    mismo_medio: 'Mismo medio de pago',
    credito_tienda: 'Credito en tienda',
    efectivo: 'Efectivo',
  };

  private extraerError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
    }
    return 'No se pudo completar la accion.';
  }
}
