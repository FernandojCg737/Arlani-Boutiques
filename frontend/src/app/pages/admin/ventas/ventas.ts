import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { enlaceMapa } from '../../../services/mapa';
import { AdminCambios } from '../cambios/cambios';
import { Origen, SelectorOrigen } from '../../../components/selector-origen/selector-origen';

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
  metodo_pago_nombre: string | null;
  motivo_rechazo: string | null;
  envio: EnvioVenta | null;
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

interface EnvioVenta {
  destinatario: string;
  telefono: string | null;
  direccion: string;
  referencia: string | null;
  ciudad: string | null;
  latitud: string;
  longitud: string;
  estado: 'pendiente' | 'enviado' | 'entregado';
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

interface VarianteMostrador {
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  stock: number;
}

interface QrTienda {
  id: number;
  nombre: string;
  qr_url: string;
  instrucciones: string | null;
  banco: string | null;
  titular: string | null;
}

interface ProductoMostrador {
  producto_id: number;
  nombre: string;
  precio: string;
  imagen_url: string | null;
  variantes: VarianteMostrador[];
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

type Vista = 'ventas' | 'reservas' | 'devoluciones' | 'cambios';

// CU11: panel financiero de staff (Administrador, Encargado de Sucursal,
// Cajero) -- reune ventas en linea (PayPal), por QR (con aprobacion manual)
// y de mostrador en un solo lugar, y permite registrar una venta presencial
// en efectivo.
@Component({
  selector: 'app-admin-ventas',
  imports: [DatePipe, DecimalPipe, RouterLink, AdminCambios, SelectorOrigen],
  templateUrl: './ventas.html',
  styleUrl: './ventas.scss',
})
export class AdminVentas implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  // ONLINE / OFFLINE (las hechas sin conexion llegan al sincronizar, CU12):
  // solo si el plan de la tienda incluye la operacion sin conexion (Basico y
  // Profesional). Lo ve el personal (CU11) y el SuperAdministrador (CU06).
  protected readonly conOrigen = signal(false);
  protected readonly esPlataforma = this.route.snapshot.data['origenes'] === true;
  protected readonly planSinOffline = signal<string | null>(null);
  protected readonly origen = signal<Origen>(
    this.route.snapshot.queryParamMap.get('origen') === 'offline' ? 'offline' : 'online',
  );

  protected cambiarOrigen(o: Origen): void {
    if (o === this.origen()) return;
    this.origen.set(o);
    // OFFLINE muestra solo las ventas sincronizadas.
    if (o === 'offline') this.vista.set('ventas');
    void this.router.navigate([], { queryParams: { origen: o }, queryParamsHandling: 'merge', replaceUrl: true });
    this.filtrar();
  }

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
  protected readonly cantidadNueva = signal(1);
  protected readonly itemsNuevaVenta = signal<ItemNuevaVenta[]>([]);
  protected readonly guardandoVenta = signal(false);
  protected readonly errorNuevaVenta = signal('');

  // Catalogo de la sucursal: prendas con stock, como al pedir un cambio
  // (producto -> talla -> color, con cuantas quedan).
  protected readonly catalogoMostrador = signal<ProductoMostrador[]>([]);
  protected readonly cargandoCatalogo = signal(false);
  protected readonly productoBusqueda = signal('');
  protected readonly productoElegidoId = signal<number | null>(null);
  protected readonly tallaElegida = signal<number | null>(null);
  protected readonly colorElegido = signal<number | null>(null);

  protected readonly productosFiltrados = computed(() => {
    const termino = this.productoBusqueda().trim().toLowerCase();
    const todos = this.catalogoMostrador();
    return termino ? todos.filter((p) => p.nombre.toLowerCase().includes(termino)) : todos;
  });
  protected readonly productoElegido = computed(
    () => this.catalogoMostrador().find((p) => p.producto_id === this.productoElegidoId()) ?? null,
  );
  protected readonly tallasProducto = computed(() => {
    const vistas = new Map<number, string>();
    for (const v of this.productoElegido()?.variantes ?? []) vistas.set(v.talla_id, v.talla_codigo);
    return [...vistas].map(([id, codigo]) => ({ id, codigo }));
  });
  protected readonly coloresTalla = computed(() =>
    (this.productoElegido()?.variantes ?? []).filter((v) => v.talla_id === this.tallaElegida()),
  );
  protected readonly varianteElegida = computed(
    () => this.coloresTalla().find((v) => v.color_id === this.colorElegido()) ?? null,
  );

  // Cobro de la venta de mostrador: efectivo o QR (foto del comprobante opcional).
  protected readonly metodoCobro = signal<'efectivo' | 'qr'>('efectivo');
  protected readonly fotoComprobante = signal<string | null>(null);
  // QR de cobro de la tienda (Metodos de pago) que se le muestra al cliente.
  protected readonly qrsTienda = signal<QrTienda[]>([]);
  protected readonly qrElegidoId = signal<number | null>(null);
  protected readonly qrElegido = computed(
    () => this.qrsTienda().find((q) => q.id === this.qrElegidoId()) ?? this.qrsTienda()[0] ?? null,
  );

  // Cliente de la venta de mostrador: con cuenta (se busca) o sin cuenta
  // (solo su nombre); en ambos casos, NIT o CI opcional para la factura.
  protected readonly tipoCliente = signal<'cuenta' | 'sin_cuenta'>('sin_cuenta');
  protected readonly facturaNombre = signal('');
  protected readonly facturaNit = signal('');

  // Lo que falta para poder cobrar (se le dice al empleado bajo el boton).
  protected readonly faltaParaCobrar = computed(() => {
    if (this.editando()) return this.itemsNuevaVenta().length ? [] : ['Agrega al menos una prenda.'];
    const falta: string[] = [];
    if (this.tipoCliente() === 'sin_cuenta') {
      if (this.facturaNombre().trim().length < 2) falta.push('Escribe el nombre del cliente.');
    } else if (!this.clienteSeleccionado()) {
      falta.push(
        this.clienteBusqueda().trim()
          ? 'Elige al cliente en la lista de sugerencias (toca su nombre).'
          : 'Busca y elige al cliente por su nombre o correo.',
      );
    }
    if (this.itemsNuevaVenta().length === 0) falta.push('Agrega al menos una prenda a la venta.');
    return falta;
  });

  protected readonly totalNuevaVenta = computed(() =>
    this.itemsNuevaVenta().reduce((sum, i) => sum + i.precio_unitario * i.cantidad, 0),
  );

  ngOnInit(): void {
    this.cargarSucursales();
    void this.iniciar();
  }

  private async iniciar(): Promise<void> {
    try {
      const r = await firstValueFrom(
        this.http.get<{ offline: boolean; plan: string | null }>(`${environment.apiUrl}/ventas/origenes`),
      );
      this.conOrigen.set(r.offline);
      this.planSinOffline.set(r.offline ? null : r.plan);
    } catch {
      this.conOrigen.set(false);
    }
    if (!this.conOrigen() && this.origen() === 'offline') this.origen.set('online');
    await this.load();
  }

  private async cargarSucursales(): Promise<void> {
    try {
      // Solo las sucursales de la tienda (las publicas son de todas las
      // tiendas); el Cajero y el Encargado, solo la suya.
      this.sucursales.set(
        await firstValueFrom(this.http.get<Sucursal[]>(`${environment.apiUrl}/ventas/presencial/sucursales`)),
      );
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

  // Si se cambia de ONLINE a OFFLINE (o de filtro) antes de que llegue la
  // respuesta anterior, solo cuenta la de la última consulta.
  private consulta = 0;

  private async load(): Promise<void> {
    const esta = ++this.consulta;
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
      if (this.conOrigen()) params['origen'] = this.origen();

      const res = await firstValueFrom(this.http.get<VentaPage>(`${environment.apiUrl}/ventas`, { params }));
      if (esta !== this.consulta) return;
      this.items.set(res.items);
      this.total.set(res.total);
    } catch {
      if (esta === this.consulta) this.error.set('No se pudo cargar las ventas.');
    } finally {
      if (esta === this.consulta) this.loading.set(false);
    }
  }

  // CU21: los pagos con comprobante (QR, transferencia u otro metodo de la
  // tienda) los aprueba o rechaza el Administrador, Encargado o Cajero.
  protected nombreMetodo(v: VentaItem): string {
    return v.metodo_pago_nombre ?? this.metodosPagoLabels[v.metodo_pago] ?? v.metodo_pago;
  }

  // Envio a domicilio: la direccion del momento de la compra y su estado.
  protected readonly enlaceMapa = enlaceMapa;
  protected readonly estadoEnvioLabel: Record<string, string> = {
    pendiente: 'Por enviar',
    enviado: 'En camino',
    entregado: 'Entregado',
  };

  protected async marcarEnvio(venta: VentaItem, estado: 'enviado' | 'entregado'): Promise<void> {
    this.procesando.set(venta.id);
    this.error.set('');
    try {
      const nueva = await firstValueFrom(
        this.http.post<VentaItem>(`${environment.apiUrl}/ventas/${venta.id}/envio`, { estado }),
      );
      this.items.update((vs) => vs.map((x) => (x.id === nueva.id ? nueva : x)));
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  protected async aprobarPago(venta: VentaItem): Promise<void> {
    if (!confirm(`¿Aprobar el pago (${this.nombreMetodo(venta)}) de la venta #${venta.id}? Esto descuenta el stock.`)) return;
    this.procesando.set(venta.id);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/ventas/${venta.id}/aprobar-pago`, {}));
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  // Compra sin conexión pagada contra entrega: cobrada al entregar, o anulada
  // (no se entregó) y el stock vuelve.
  protected async contraEntrega(venta: VentaItem, accion: 'cobrar' | 'anular'): Promise<void> {
    let motivo: string | null = null;
    if (accion === 'cobrar') {
      if (!confirm(`¿Confirmas que cobraste Bs ${venta.total} de la venta #${venta.id} al entregarla?`)) return;
    } else {
      motivo = prompt('¿Por qué se anula? (el stock vuelve a la sucursal)', 'No se pudo entregar.');
      if (motivo === null) return;
    }
    this.procesando.set(venta.id);
    this.error.set('');
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/ventas/${venta.id}/contra-entrega/${accion}`, motivo ? { motivo } : {}),
      );
      await this.load();
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.procesando.set(null);
    }
  }

  protected readonly rechazando = signal<VentaItem | null>(null);
  protected readonly motivoRechazo = signal('');
  protected readonly errorRechazo = signal('');
  protected readonly motivosRapidos = [
    'El monto del comprobante no coincide con el total.',
    'No encontramos el depósito en nuestra cuenta.',
    'La foto del comprobante no se lee bien.',
  ];

  protected abrirRechazo(venta: VentaItem): void {
    this.rechazando.set(venta);
    this.motivoRechazo.set('');
    this.errorRechazo.set('');
  }

  protected cerrarRechazo(): void {
    this.rechazando.set(null);
  }

  protected async confirmarRechazo(): Promise<void> {
    const venta = this.rechazando();
    const motivo = this.motivoRechazo().trim();
    if (!venta) return;
    if (motivo.length < 3) {
      this.errorRechazo.set('Escribe el motivo: el cliente lo verá en Mis compras.');
      return;
    }
    this.procesando.set(venta.id);
    this.errorRechazo.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/ventas/${venta.id}/rechazar-pago`, { motivo }));
      this.rechazando.set(null);
      await this.load();
    } catch (err) {
      this.errorRechazo.set(this.extraerError(err));
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
    this.metodoCobro.set('efectivo');
    this.fotoComprobante.set(null);
    this.tipoCliente.set('sin_cuenta');
    this.facturaNombre.set('');
    this.facturaNit.set('');
    this.limpiarSeleccionProducto();
    void this.cargarCatalogoMostrador();
    void this.cargarQrsTienda();
  }

  private async cargarQrsTienda(): Promise<void> {
    try {
      const qrs = await firstValueFrom(this.http.get<QrTienda[]>(`${environment.apiUrl}/ventas/presencial/qr`));
      this.qrsTienda.set(qrs);
      this.qrElegidoId.set(qrs[0]?.id ?? null);
    } catch {
      this.qrsTienda.set([]);
    }
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
    void this.cargarCatalogoMostrador();
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
    // Si cambia lo escrito, el cliente elegido antes ya no vale.
    if (this.clienteSeleccionado() && this.clienteSeleccionado()!.nombre !== termino) this.clienteSeleccionado.set(null);
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
      // Lo escrito es exactamente un cliente (nombre o correo): queda elegido.
      const exacto = res.filter(
        (c) => c.nombre.toLowerCase() === termino.toLowerCase() || c.email.toLowerCase() === termino.toLowerCase(),
      );
      if (exacto.length === 1 && this.clienteBusqueda().trim() === termino) {
        this.seleccionarCliente(exacto[0]);
        return;
      }
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
    this.productoElegidoId.set(null);
    this.tallaElegida.set(null);
    this.colorElegido.set(null);
    this.cantidadNueva.set(1);
  }

  // Prendas con stock en la sucursal elegida (se recarga al cambiarla).
  protected async cargarCatalogoMostrador(): Promise<void> {
    const sucursalId = this.sucursalNuevaId();
    this.catalogoMostrador.set([]);
    this.limpiarSeleccionProducto();
    if (!sucursalId) return;
    this.cargandoCatalogo.set(true);
    try {
      this.catalogoMostrador.set(
        await firstValueFrom(
          this.http.get<ProductoMostrador[]>(`${environment.apiUrl}/ventas/presencial/catalogo`, {
            params: { sucursal_id: String(sucursalId) },
          }),
        ),
      );
    } catch {
      this.catalogoMostrador.set([]);
    } finally {
      this.cargandoCatalogo.set(false);
    }
  }

  protected cambiarSucursal(id: number): void {
    this.sucursalNuevaId.set(id);
    // Las prendas ya agregadas eran de la otra sucursal.
    if (!this.editando()) this.itemsNuevaVenta.set([]);
    void this.cargarCatalogoMostrador();
  }

  protected elegirProducto(p: ProductoMostrador): void {
    this.productoElegidoId.set(p.producto_id);
    this.tallaElegida.set(null);
    this.colorElegido.set(null);
    this.cantidadNueva.set(1);
    const tallas = new Set(p.variantes.filter((v) => this.disponibles(p, v) > 0).map((v) => v.talla_id));
    if (tallas.size === 1) this.elegirTalla([...tallas][0]);
  }

  protected elegirTalla(id: number): void {
    this.tallaElegida.set(id);
    const p = this.productoElegido();
    const colores = (p?.variantes ?? []).filter((v) => v.talla_id === id && p && this.disponibles(p, v) > 0);
    this.colorElegido.set(colores.length === 1 ? colores[0].color_id : null);
    this.cantidadNueva.set(1);
  }

  // Stock de la variante menos lo que ya se agrego a esta venta.
  protected disponibles(p: ProductoMostrador, v: VarianteMostrador): number {
    const enVenta = this.itemsNuevaVenta()
      .filter((i) => i.producto_id === p.producto_id && i.talla_id === v.talla_id && i.color_id === v.color_id)
      .reduce((s, i) => s + i.cantidad, 0);
    return v.stock - (this.editando() ? 0 : enVenta);
  }

  protected tallaConStock(p: ProductoMostrador, tallaId: number): boolean {
    return p.variantes.some((v) => v.talla_id === tallaId && this.disponibles(p, v) > 0);
  }

  protected agregarItem(): void {
    const producto = this.productoElegido();
    const variante = this.varianteElegida();
    const cantidad = this.cantidadNueva();
    if (!producto || !variante || cantidad < 1 || cantidad > this.disponibles(producto, variante)) return;

    // La misma prenda (talla y color) se suma en una sola linea.
    this.itemsNuevaVenta.update((items) => {
      const igual = items.find(
        (i) => i.producto_id === producto.producto_id && i.talla_id === variante.talla_id && i.color_id === variante.color_id,
      );
      if (igual) return items.map((i) => (i === igual ? { ...i, cantidad: i.cantidad + cantidad } : i));
      return [
        ...items,
        {
          producto_id: producto.producto_id,
          producto_nombre: producto.nombre,
          talla_id: variante.talla_id,
          talla_codigo: variante.talla_codigo,
          color_id: variante.color_id,
          color_nombre: variante.color_nombre,
          cantidad,
          precio_unitario: Number(producto.precio),
        },
      ];
    });
    this.limpiarSeleccionProducto();
  }

  // Foto del comprobante del QR (desde la camara en el celular o tablet).
  protected alTomarFoto(input: HTMLInputElement): void {
    const archivo = input.files?.[0];
    input.value = '';
    if (!archivo) return;
    if (archivo.size > 5 * 1024 * 1024) {
      this.errorNuevaVenta.set('La foto pesa más de 5 MB. Toma otra con menos resolución.');
      return;
    }
    const lector = new FileReader();
    lector.onload = () => this.fotoComprobante.set(String(lector.result));
    lector.readAsDataURL(archivo);
  }

  protected quitarItem(index: number): void {
    this.itemsNuevaVenta.update((items) => items.filter((_, i) => i !== index));
  }

  protected async confirmarVenta(): Promise<void> {
    const sucursalId = this.sucursalNuevaId();
    const items = this.itemsNuevaVenta();
    const edit = this.editando();
    if (!sucursalId || items.length === 0 || this.faltaParaCobrar().length > 0) return;
    const conCuenta = this.tipoCliente() === 'cuenta';

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
            cliente_id: conCuenta ? this.clienteSeleccionado()!.id : null,
            factura_nombre: conCuenta ? null : this.facturaNombre().trim(),
            factura_nit: this.facturaNit().trim() || null,
            sucursal_id: sucursalId,
            items: itemsPayload,
            metodo_pago: this.metodoCobro(),
            metodo_pago_id: this.metodoCobro() === 'qr' ? (this.qrElegido()?.id ?? null) : null,
            comprobante: this.metodoCobro() === 'qr' ? this.fotoComprobante() : null,
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

  // Rechazar una devolucion pide el motivo: el cliente lo ve en su
  // notificacion y en el correo que le llega.
  protected readonly devolucionRechazando = signal<DevolucionItem | null>(null);
  protected readonly motivoDevolucion = signal('');
  protected readonly errorRechazoDevolucion = signal('');
  protected readonly motivosDevolucion = [
    'La prenda tiene señales de uso',
    'Ya pasó el plazo para devolverla',
    'La prenda no tiene sus etiquetas',
    'No coincide con la compra',
  ];

  protected rechazarDevolucion(dev: DevolucionItem): void {
    this.devolucionVerModal.set(null);
    this.motivoDevolucion.set('');
    this.errorRechazoDevolucion.set('');
    this.devolucionRechazando.set(dev);
  }

  protected cerrarRechazoDevolucion(): void {
    this.devolucionRechazando.set(null);
  }

  protected async confirmarRechazoDevolucion(): Promise<void> {
    const dev = this.devolucionRechazando();
    const motivo = this.motivoDevolucion().trim();
    if (!dev) return;
    if (motivo.length < 3) {
      this.errorRechazoDevolucion.set('Escribe el motivo: el cliente lo verá.');
      return;
    }
    this.procesando.set(dev.id);
    this.errorRechazoDevolucion.set('');
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/devoluciones/${dev.id}/rechazar`, { motivo }));
      this.devolucionRechazando.set(null);
      await this.cargarDevoluciones();
      await this.load();
    } catch (err) {
      this.errorRechazoDevolucion.set(this.extraerError(err));
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

  protected readonly metodosPagoLabels: Record<string, string> = {
    efectivo: 'Efectivo',
    paypal: 'PayPal',
    qr: 'QR',
    transferencia: 'Transferencia',
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
