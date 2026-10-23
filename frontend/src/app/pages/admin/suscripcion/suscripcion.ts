import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { EstadoTienda } from '../../../services/estado-tienda';
import { MarcaEmpresa, MarcaTienda } from '../../../services/marca-tienda';
import { PaypalSdk } from '../../../services/paypal-sdk';
import { enlaceTienda, mensajeError, rutaTienda } from '../../../services/plataforma';

const LOGO_MAX_BYTES = 5 * 1024 * 1024;

interface PlanDisponible {
  codigo: string;
  nombre: string;
  precio_mensual: string;
  max_sucursales: number;
  dias_prueba: number | null;
  ia_generativa: boolean;
  operacion_offline: boolean;
  comision_pct: string;
}

interface CotizacionRenovacion {
  plan_codigo: string;
  plan_nombre: string;
  periodo: 'mensual' | 'anual';
  monto_bob: string;
  tipo_cambio: string;
  monto_usd: string;
  plan_bob: string;
  plan_usd: string;
  comisiones_bob: string;
  comisiones_usd: string;
  fecha_inicio: string;
}

interface MovimientoCuenta {
  id: number;
  fecha: string;
  tipo: 'comision' | 'pago' | 'ajuste';
  venta_id: number | null;
  base_bob: string | null;
  porcentaje: string | null;
  monto_bob: string;
  descripcion: string;
}

interface LiquidacionRecibida {
  id: number;
  fecha: string;
  bruto_bob: string;
  comision_bob: string;
  neto_bob: string;
  neto_usd: string;
  paypal_email: string;
  estado: 'pendiente' | 'enviada' | 'fallida';
}

interface CuentaTienda {
  liquidaciones: LiquidacionRecibida[];
  saldo_bob: string;
  saldo_usd: string;
  tipo_cambio: string;
  comision_pct: string | null;
  ventas_mes: number;
  ventas_mes_bob: string;
  comisiones_mes_bob: string;
  pagado_total_bob: string;
  movimientos: MovimientoCuenta[];
}

interface HistorialSuscripcion {
  id: number;
  plan_nombre: string;
  periodo: string;
  monto: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  estado: string;
}

interface MiSuscripcion {
  empresa_id: number;
  empresa_nombre: string;
  subdominio: string;
  color_marca: string;
  empresa_estado: 'activa' | 'suspendida';
  plan_codigo: string | null;
  plan_nombre: string | null;
  precio_mensual: string | null;
  ia_generativa: boolean | null;
  periodo: 'mensual' | 'anual' | 'prueba' | null;
  monto: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  dias_restantes: number | null;
  sucursales_usadas: number;
  max_sucursales: number | null;
  personal: number;
  clientes: number;
  // False: la suscripcion vencio (o la tienda esta suspendida) y no opera.
  operativa: boolean;
  comision_pct: string | null;
  historial: HistorialSuscripcion[];
  planes: PlanDisponible[];
}

// Soporte de Arlani: los cambios de plan los aplica el SuperAdministrador.
const WHATSAPP_SOPORTE = '59173766956';
const AVISO_DIAS = 15;

// Mi suscripcion: el Administrador de la tienda ve su plan, cuando vence,
// cuanto usa de el, el enlace de su tienda y los planes a los que puede pasar.
// Desde aca compra o renueva su plan con PayPal; con la suscripcion vencida
// es lo unico que la tienda puede hacer.
@Component({
  selector: 'app-admin-suscripcion',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './suscripcion.html',
  styleUrl: './suscripcion.scss',
})
export class AdminSuscripcion {
  private readonly http = inject(HttpClient);
  private readonly paypalSdk = inject(PaypalSdk);
  private readonly estadoTienda = inject(EstadoTienda);

  protected readonly datos = signal<MiSuscripcion | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly copiado = signal(false);

  // Tu marca: logo y color de la tienda (el panel se pinta con ellos).
  protected readonly marca = inject(MarcaTienda);
  protected readonly colorNuevo = signal<string | null>(null);
  protected readonly logoNuevo = signal<string | null>(null);
  protected readonly guardandoMarca = signal(false);
  protected readonly avisoMarca = signal('');
  protected readonly errorMarca = signal('');
  protected readonly colorVista = computed(() => this.colorNuevo() ?? this.marca.marca()?.color_marca ?? '#1f2a44');
  protected readonly logoVista = computed(() => this.logoNuevo() ?? this.marca.logo());
  protected readonly hayCambiosMarca = computed(() => this.colorNuevo() !== null || this.logoNuevo() !== null);

  protected readonly textoPeriodo: Record<string, string> = {
    mensual: 'Pago mensual',
    anual: 'Pago anual',
    prueba: 'Periodo de prueba',
  };
  protected readonly textoEstado: Record<string, string> = {
    activa: 'Vigente',
    reemplazada: 'Reemplazada',
    cancelada: 'Cancelada',
    vencida: 'Vencida',
  };

  protected readonly enlace = computed(() => {
    const d = this.datos();
    return d ? enlaceTienda(d.subdominio) : '';
  });
  protected readonly ruta = computed(() => {
    const d = this.datos();
    return d ? rutaTienda(d.subdominio) : '/';
  });

  // Uso de sucursales (0-100) para la barra.
  protected readonly usoSucursales = computed(() => {
    const d = this.datos();
    if (!d?.max_sucursales) return 0;
    return Math.min(100, Math.round((d.sucursales_usadas / d.max_sucursales) * 100));
  });

  // Aviso arriba: suspendida, sin plan, vencida o por vencer.
  protected readonly aviso = computed<{ tono: 'alerta' | 'info'; texto: string } | null>(() => {
    const d = this.datos();
    if (!d) return null;
    if (d.empresa_estado === 'suspendida')
      return { tono: 'alerta', texto: 'Tu tienda está suspendida. Escríbenos a soporte para reactivarla.' };
    if (!d.plan_codigo) return { tono: 'alerta', texto: 'Tu tienda no tiene una suscripción vigente.' };
    const dias = d.dias_restantes;
    if (!d.operativa || (dias !== null && dias < 0))
      return {
        tono: 'alerta',
        texto:
          'Tu suscripción venció y tu tienda está pausada: no aparece en la plataforma ni puede vender. ' +
          'Renueva tu plan abajo para volver a operar.',
      };
    if (dias !== null && dias <= AVISO_DIAS)
      return {
        tono: 'info',
        texto:
          dias === 0
            ? 'Tu suscripción vence hoy.'
            : `Tu suscripción vence en ${dias} ${dias === 1 ? 'día' : 'días'}.`,
      };
    return null;
  });

  protected alElegirLogo(input: HTMLInputElement): void {
    const archivo = input.files?.[0];
    input.value = '';
    this.errorMarca.set('');
    this.avisoMarca.set('');
    if (!archivo) return;
    if (archivo.size > LOGO_MAX_BYTES) {
      this.errorMarca.set('El logo pesa más de 5 MB. Elige una imagen más liviana.');
      return;
    }
    const lector = new FileReader();
    lector.onload = () => this.logoNuevo.set(String(lector.result));
    lector.onerror = () => this.errorMarca.set('No pudimos leer la imagen. Prueba con otra.');
    lector.readAsDataURL(archivo);
  }

  protected alElegirColor(valor: string): void {
    this.avisoMarca.set('');
    this.colorNuevo.set(valor.toLowerCase());
  }

  protected descartarMarca(): void {
    this.colorNuevo.set(null);
    this.logoNuevo.set(null);
    this.errorMarca.set('');
  }

  protected async guardarMarca(): Promise<void> {
    this.guardandoMarca.set(true);
    this.errorMarca.set('');
    try {
      const nueva = await firstValueFrom(
        this.http.put<MarcaEmpresa>(`${environment.apiUrl}/mi-empresa/marca`, {
          color_marca: this.colorNuevo(),
          logo: this.logoNuevo(),
        }),
      );
      // El panel toma la marca nueva al instante.
      this.marca.marca.set(nueva);
      this.descartarMarca();
      this.avisoMarca.set('Listo: tu panel, tus reportes y tu tienda ya usan tu marca.');
    } catch (err) {
      this.errorMarca.set(mensajeError(err, 'No pudimos guardar tu marca. Inténtalo de nuevo.'));
    } finally {
      this.guardandoMarca.set(false);
    }
  }

  constructor() {
    void this.cargar();
    void this.cargarCuenta();
  }

  // ------------------------------------------------ estado de cuenta
  // Comision de Arlani por cada venta en linea; se paga con PayPal cuando la
  // tienda quiera o junto con la renovacion del plan.
  protected readonly cuenta = signal<CuentaTienda | null>(null);
  protected readonly verTodos = signal(false);
  protected readonly pagandoSaldo = signal(false);
  protected readonly procesandoSaldo = signal(false);
  protected readonly errorSaldo = signal('');
  protected readonly exitoSaldo = signal('');
  private readonly contenedorPaypalSaldo = viewChild<ElementRef<HTMLDivElement>>('paypalSaldo');

  protected readonly movimientosVisibles = computed(() => {
    const m = this.cuenta()?.movimientos ?? [];
    return this.verTodos() ? m : m.slice(0, 8);
  });

  protected absoluto(valor: string): number {
    return Math.abs(Number(valor));
  }

  private async cargarCuenta(): Promise<void> {
    try {
      this.cuenta.set(await firstValueFrom(this.http.get<CuentaTienda>(`${environment.apiUrl}/mi-empresa/cuenta`)));
    } catch {
      // Sin estado de cuenta la pantalla sigue funcionando.
    }
  }

  protected async abrirPagoSaldo(): Promise<void> {
    this.pagandoSaldo.set(true);
    this.errorSaldo.set('');
    this.exitoSaldo.set('');
    await new Promise((r) => setTimeout(r));
    const contenedor = this.contenedorPaypalSaldo()?.nativeElement;
    if (!contenedor) return;
    contenedor.innerHTML = '';
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const paypal = (await this.paypalSdk.cargar()) as any;
      await paypal
        .Buttons({
          style: { layout: 'vertical', shape: 'pill', label: 'pay' },
          createOrder: async () =>
            (await firstValueFrom(this.http.post<{ order_id: string }>(`${environment.apiUrl}/mi-empresa/cuenta/orden`, {})))
              .order_id,
          onApprove: (data: { orderID: string }) => this.confirmarPagoSaldo(data.orderID),
          onCancel: () => this.errorSaldo.set('Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.'),
          onError: (err: unknown) =>
            this.errorSaldo.set(mensajeError(err, 'PayPal tuvo un problema. Inténtalo de nuevo en unos segundos.')),
        })
        .render(contenedor);
    } catch {
      this.errorSaldo.set('No se pudo cargar PayPal. Inténtalo de nuevo en unos segundos.');
    }
  }

  private async confirmarPagoSaldo(orderId: string): Promise<void> {
    this.procesandoSaldo.set(true);
    this.errorSaldo.set('');
    try {
      const pagado = this.cuenta()?.saldo_bob;
      this.cuenta.set(
        await firstValueFrom(
          this.http.post<CuentaTienda>(`${environment.apiUrl}/mi-empresa/cuenta/confirmar`, { order_id: orderId }),
        ),
      );
      this.pagandoSaldo.set(false);
      this.exitoSaldo.set(`Listo: pagaste Bs ${pagado} de comisiones. Tu cuenta quedó al día.`);
    } catch (err) {
      this.errorSaldo.set(mensajeError(err, 'No pudimos registrar tu pago.'));
    } finally {
      this.procesandoSaldo.set(false);
    }
  }

  private async cargar(): Promise<void> {
    try {
      this.datos.set(
        await firstValueFrom(this.http.get<MiSuscripcion>(`${environment.apiUrl}/mi-empresa/suscripcion`)),
      );
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar tu suscripción.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected async copiarEnlace(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.enlace());
      this.copiado.set(true);
      setTimeout(() => this.copiado.set(false), 2000);
    } catch {
      // sin portapapeles (http sin permisos): el enlace igual se puede seleccionar
    }
  }

  // ------------------------------------------------ comprar / renovar
  protected readonly planPago = signal<PlanDisponible | null>(null);
  protected readonly periodoPago = signal<'mensual' | 'anual'>('mensual');
  protected readonly cotizacion = signal<CotizacionRenovacion | null>(null);
  protected readonly cotizando = signal(false);
  protected readonly procesando = signal(false);
  protected readonly errorPago = signal('');
  protected readonly exitoPago = signal('');
  private readonly contenedorPaypal = viewChild<ElementRef<HTMLDivElement>>('paypal');

  protected abrirPago(p: PlanDisponible): void {
    this.planPago.set(p);
    this.periodoPago.set('mensual');
    this.exitoPago.set('');
    void this.cotizarPago();
    setTimeout(() => document.getElementById('pago')?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  }

  protected cerrarPago(): void {
    this.planPago.set(null);
    this.cotizacion.set(null);
    this.errorPago.set('');
  }

  protected elegirPeriodo(periodo: 'mensual' | 'anual'): void {
    if (this.periodoPago() === periodo) return;
    this.periodoPago.set(periodo);
    void this.cotizarPago();
  }

  private solicitudPago(): { plan: string; periodo: 'mensual' | 'anual' } {
    return { plan: this.planPago()!.codigo, periodo: this.periodoPago() };
  }

  private async cotizarPago(): Promise<void> {
    if (!this.planPago()) return;
    this.cotizando.set(true);
    this.errorPago.set('');
    this.cotizacion.set(null);
    try {
      this.cotizacion.set(
        await firstValueFrom(
          this.http.post<CotizacionRenovacion>(`${environment.apiUrl}/mi-empresa/suscripcion/cotizar`, this.solicitudPago()),
        ),
      );
    } catch (err) {
      this.errorPago.set(mensajeError(err, 'No pudimos calcular el precio. Inténtalo de nuevo.'));
      return;
    } finally {
      this.cotizando.set(false);
    }
    await this.mostrarPaypal();
  }

  private async mostrarPaypal(): Promise<void> {
    // Esperar a que Angular pinte el contenedor.
    await new Promise((r) => setTimeout(r));
    const contenedor = this.contenedorPaypal()?.nativeElement;
    if (!contenedor) return;
    contenedor.innerHTML = '';
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const paypal = (await this.paypalSdk.cargar()) as any;
      await paypal
        .Buttons({
          style: { layout: 'vertical', shape: 'pill', label: 'pay' },
          createOrder: async () =>
            (
              await firstValueFrom(
                this.http.post<{ order_id: string }>(
                  `${environment.apiUrl}/mi-empresa/suscripcion/orden`,
                  this.solicitudPago(),
                ),
              )
            ).order_id,
          onApprove: (data: { orderID: string }) => this.confirmarPago(data.orderID),
          onCancel: () => this.errorPago.set('Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.'),
          onError: (err: unknown) =>
            this.errorPago.set(mensajeError(err, 'PayPal tuvo un problema. Inténtalo de nuevo en unos segundos.')),
        })
        .render(contenedor);
    } catch {
      this.errorPago.set('No se pudo cargar PayPal. Inténtalo de nuevo en unos segundos.');
    }
  }

  private async confirmarPago(orderId: string): Promise<void> {
    this.procesando.set(true);
    this.errorPago.set('');
    try {
      const res = await firstValueFrom(
        this.http.post<MiSuscripcion>(`${environment.apiUrl}/mi-empresa/suscripcion/confirmar`, {
          ...this.solicitudPago(),
          order_id: orderId,
        }),
      );
      this.datos.set(res);
      this.planPago.set(null);
      this.cotizacion.set(null);
      this.exitoPago.set(
        `Listo: tu plan ${res.plan_nombre} quedó activo` +
          (res.fecha_fin ? ` hasta el ${new Date(res.fecha_fin + 'T00:00').toLocaleDateString('es-BO')}` : '') +
          '. Tu tienda ya está operando.',
      );
      this.estadoTienda.vencida.set(false);
      void this.cargarCuenta();
      await this.marca.recargar();
    } catch (err) {
      this.errorPago.set(mensajeError(err, 'No pudimos registrar tu pago.'));
    } finally {
      this.procesando.set(false);
    }
  }

  // Un plan mas chico no alcanza si ya tiene mas sucursales activas.
  protected noAlcanza(p: PlanDisponible): boolean {
    return (this.datos()?.sucursales_usadas ?? 0) > p.max_sucursales;
  }

  protected esMejora(p: PlanDisponible): boolean {
    return Number(p.precio_mensual) > Number(this.datos()?.precio_mensual ?? 0);
  }

  // El cambio lo aplica soporte: se abre WhatsApp con el pedido ya escrito.
  protected enlaceCambio(p: PlanDisponible | null): string {
    const d = this.datos();
    if (!d) return '#';
    const texto = p
      ? `Hola, soy el administrador de ${d.empresa_nombre} (${d.subdominio}). ` +
        `Quiero cambiar mi plan ${d.plan_nombre ?? 'actual'} al plan ${p.nombre}.`
      : `Hola, soy el administrador de ${d.empresa_nombre} (${d.subdominio}). Necesito ayuda con mi suscripción.`;
    return `https://wa.me/${WHATSAPP_SOPORTE}?text=${encodeURIComponent(texto)}`;
  }
}
