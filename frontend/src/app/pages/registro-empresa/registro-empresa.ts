import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { PLANES, Periodo, Plan, esPrueba, precioAnual, precioPorMes } from '../../data/planes';
import { Auth } from '../../services/auth';
import { PaypalSdk } from '../../services/paypal-sdk';
import { enlaceDisponible, enlaceTiendaCorto, rutaTienda } from '../../services/plataforma';
import {
  Cotizacion,
  RegistroEmpresaApi,
  SolicitudSuscripcion,
  SuscripcionCreada,
} from '../../services/registro-empresa';

type Paso = 0 | 1 | 2;
const ULTIMO_PASO: Paso = 2;

const CIUDADES = ['Santa Cruz', 'La Paz', 'Cochabamba', 'Sucre', 'Tarija', 'Oruro', 'Potosí', 'Trinidad', 'Cobija'];

// Colores de marca sugeridos; con el selector RGB se elige cualquier otro.
const COLORES = [
  { nombre: 'Azul noche', valor: '#1f2a44' },
  { nombre: 'Coral', valor: '#c4503d' },
  { nombre: 'Verde botella', valor: '#203c40' },
  { nombre: 'Vino', valor: '#6d2338' },
  { nombre: 'Negro', valor: '#141414' },
  { nombre: 'Arena', valor: '#a07d5a' },
];

const LOGO_MAX_BYTES = 5 * 1024 * 1024;
const CORREO = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const HEX = /^#[0-9a-f]{6}$/i;

// "Mi Boutique Ñandú" -> "mi-boutique-nandu"
function aSubdominio(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 30);
}

// Alta de una boutique nueva en Arlani, en tres pasos (solo con sesión). El
// último paso cobra la suscripción con PayPal ahí mismo; al confirmarse el
// pago, el backend crea la empresa, la suscripción y su Administrador, y le
// manda las credenciales por correo. A la izquierda, una vista previa en vivo.
@Component({
  selector: 'app-registro-empresa',
  imports: [RouterLink],
  templateUrl: './registro-empresa.html',
  styleUrl: './registro-empresa.scss',
})
export class RegistroEmpresa {
  private readonly api = inject(RegistroEmpresaApi);
  private readonly paypalSdk = inject(PaypalSdk);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(Auth);
  // "arlani.onrender.com/tienda-": el enlace va por ruta, sin dominio propio.
  protected readonly prefijoEnlace = enlaceTiendaCorto();
  protected readonly rutaTienda = rutaTienda;

  protected readonly planes = PLANES;
  protected readonly esPrueba = esPrueba;
  protected readonly ciudades = CIUDADES;
  protected readonly colores = COLORES;
  protected readonly titulosPasos = ['Plan', 'Tu boutique', 'Confirmar y pagar'];

  protected readonly paso = signal<Paso>(0);
  // Se marca al intentar avanzar: recién ahí se muestran los errores.
  protected readonly intentoAvanzar = signal(false);

  // Paso 1: plan
  protected readonly planId = signal(this.leerPlanInicial());
  protected readonly periodo = signal<Periodo>(
    this.route.snapshot.queryParamMap.get('periodo') === 'anual' ? 'anual' : 'mensual',
  );
  protected readonly plan = computed<Plan>(() => PLANES.find((p) => p.id === this.planId()) ?? PLANES[0]);
  protected readonly precioMes = computed(() => precioPorMes(this.plan(), this.periodo()));
  protected readonly precioAnio = computed(() => precioAnual(this.plan()));

  // Paso 2: boutique
  protected readonly nombreBoutique = signal('');
  protected readonly subdominio = signal('');
  // Mientras el usuario no edite el enlace a mano, sigue al nombre.
  private subdominioEditado = false;
  protected readonly ciudad = signal('Santa Cruz');
  protected readonly sucursales = signal(1);
  protected readonly color = signal(COLORES[0].valor);
  protected readonly colorPropio = computed(() => !COLORES.some((c) => c.valor === this.color()));
  protected readonly logo = signal<string | null>(null);
  protected readonly logoNombre = signal('');
  protected readonly logoSinVista = signal(false);
  protected readonly errorLogo = signal('');
  protected readonly adminNombre = signal(this.auth.currentUser()?.nombre ?? '');
  protected readonly adminEmail = signal('');

  // Enlace final: si el escrito ya lo usa otra tienda, con un número al final.
  protected readonly enlaceFinal = enlaceDisponible(() => this.subdominio());
  protected readonly enlaceOcupado = computed(
    () => this.subdominio().length >= 3 && this.enlaceFinal() !== this.subdominio(),
  );
  protected readonly subdominioVista = computed(() => this.enlaceFinal() || 'tuboutique');

  protected readonly errores = computed(() => {
    const e: Record<string, string> = {};
    const max = this.plan().maxSucursales;
    if (this.nombreBoutique().trim().length < 2) e['nombreBoutique'] = 'Escribe el nombre de tu boutique.';
    if (!/^[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])$/.test(this.subdominio()))
      e['subdominio'] = 'Entre 3 y 30 letras, números o guiones (sin espacios ni acentos).';
    if (!Number.isInteger(this.sucursales()) || this.sucursales() < 1 || this.sucursales() > max)
      e['sucursales'] = `Tu plan ${this.plan().nombre} permite de 1 a ${max} ${max === 1 ? 'sucursal' : 'sucursales'}.`;
    if (this.adminNombre().trim().length < 2) e['adminNombre'] = 'Escribe el nombre del administrador.';
    if (!CORREO.test(this.adminEmail().trim())) e['adminEmail'] = 'Escribe un correo válido.';
    else if (this.adminEmail().trim().toLowerCase() === this.auth.currentUser()?.email?.toLowerCase())
      e['adminEmail'] = 'Usa un correo distinto al de tu cuenta de cliente.';
    return e;
  });

  private readonly camposPorPaso: Record<Paso, string[]> = {
    0: [],
    1: ['nombreBoutique', 'subdominio', 'sucursales', 'adminNombre', 'adminEmail'],
    2: [],
  };

  // Paso 3: cotización, pago y resultado
  protected readonly cotizacion = signal<Cotizacion | null>(null);
  protected readonly cotizando = signal(false);
  protected readonly mostrarPago = signal(false);
  protected readonly procesando = signal(false);
  protected readonly errorEnvio = signal('');
  protected readonly creada = signal<SuscripcionCreada | null>(null);
  private readonly contenedorPaypal = viewChild<ElementRef<HTMLDivElement>>('contenedorPaypal');

  protected precioDe(plan: Plan): number {
    return precioPorMes(plan, this.periodo());
  }

  protected error(campo: string): string | null {
    if (!this.intentoAvanzar()) return null;
    return this.errores()[campo] ?? null;
  }

  protected elegirPlan(id: string): void {
    this.planId.set(id);
    // Las sucursales no pueden pasar el máximo del plan nuevo.
    this.sucursales.update((n) => Math.min(Math.max(n, 1), this.plan().maxSucursales));
  }

  protected siguiente(): void {
    const invalido = this.camposPorPaso[this.paso()].some((c) => this.errores()[c]);
    if (invalido) {
      this.intentoAvanzar.set(true);
      return;
    }
    this.intentoAvanzar.set(false);
    if (this.paso() < ULTIMO_PASO) this.paso.update((p) => (p + 1) as Paso);
    if (this.paso() === ULTIMO_PASO) void this.cotizar();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  protected anterior(): void {
    this.intentoAvanzar.set(false);
    this.salirDelPago();
    if (this.paso() > 0) this.paso.update((p) => (p - 1) as Paso);
  }

  // Solo se puede saltar a pasos ya visitados (hacia atrás).
  protected irAPaso(destino: number): void {
    if (destino < this.paso()) {
      this.intentoAvanzar.set(false);
      this.salirDelPago();
      this.paso.set(destino as Paso);
    }
  }

  protected alCambiarNombre(valor: string): void {
    this.nombreBoutique.set(valor);
    if (!this.subdominioEditado) this.subdominio.set(aSubdominio(valor));
  }

  protected alCambiarSubdominio(valor: string): void {
    this.subdominioEditado = true;
    this.subdominio.set(aSubdominio(valor));
  }

  protected alCambiarSucursales(valor: string): void {
    this.sucursales.set(Math.floor(Number(valor)) || 0);
  }

  // Selector RGB y campo hexadecimal: cualquier color.
  protected alElegirColor(valor: string): void {
    const hex = valor.trim().startsWith('#') ? valor.trim() : `#${valor.trim()}`;
    if (HEX.test(hex)) this.color.set(hex.toLowerCase());
  }

  // Logo en cualquier formato de imagen: se manda como data URL y el backend
  // lo convierte. HEIC/TIFF no se pueden mostrar en el navegador: se guardan
  // igual y la vista previa muestra el nombre del archivo.
  protected alElegirLogo(input: HTMLInputElement): void {
    const archivo = input.files?.[0];
    input.value = '';
    this.errorLogo.set('');
    if (!archivo) return;
    if (archivo.size > LOGO_MAX_BYTES) {
      this.errorLogo.set('El logo pesa más de 5 MB. Elige una imagen más liviana.');
      return;
    }
    const nombre = archivo.name.toLowerCase();
    const esImagen = archivo.type.startsWith('image/') || /\.(heic|heif|avif|svg|tiff?|bmp|ico|webp)$/.test(nombre);
    if (!esImagen) {
      this.errorLogo.set('Ese archivo no es una imagen.');
      return;
    }
    const lector = new FileReader();
    lector.onload = () => {
      this.logo.set(String(lector.result));
      this.logoNombre.set(archivo.name);
      this.logoSinVista.set(false);
    };
    lector.onerror = () => this.errorLogo.set('No pudimos leer la imagen. Prueba con otra.');
    lector.readAsDataURL(archivo);
  }

  protected quitarLogo(): void {
    this.logo.set(null);
    this.logoNombre.set('');
    this.logoSinVista.set(false);
  }

  private solicitud(): SolicitudSuscripcion {
    return {
      plan: this.planId(),
      periodo: this.periodo(),
      boutique: {
        nombre: this.nombreBoutique().trim(),
        subdominio: this.subdominio(),
        ciudad: this.ciudad(),
        sucursales: this.sucursales(),
        color: this.color(),
      },
      administrador: { nombre: this.adminNombre().trim(), email: this.adminEmail().trim().toLowerCase() },
    };
  }

  // Al llegar a "Confirmar": precio en Bs y USD, y validación antes de cobrar
  // (correo del administrador libre, sucursales dentro del plan).
  private async cotizar(): Promise<void> {
    this.cotizacion.set(null);
    this.errorEnvio.set('');
    this.cotizando.set(true);
    try {
      this.cotizacion.set(await this.api.cotizar(this.solicitud()));
    } catch (err) {
      this.errorEnvio.set(this.mensaje(err, 'No pudimos calcular el precio. Revisa tu conexión e inténtalo de nuevo.'));
    } finally {
      this.cotizando.set(false);
    }
  }

  protected reintentarCotizacion(): void {
    void this.cotizar();
  }

  // "Pagar mi suscripción": muestra los botones de PayPal ahí mismo.
  protected async pagar(): Promise<void> {
    this.errorEnvio.set('');
    this.mostrarPago.set(true);
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
          createOrder: () => this.api.crearOrden(this.solicitud()),
          onApprove: async (data: { orderID: string }) => {
            await this.confirmar(data.orderID);
          },
          onCancel: () => this.errorEnvio.set('Cancelaste el pago. Puedes intentarlo de nuevo cuando quieras.'),
          onError: (err: unknown) =>
            this.errorEnvio.set(this.mensaje(err, 'PayPal tuvo un problema. Inténtalo de nuevo en unos segundos.')),
        })
        .render(contenedor);
    } catch {
      this.errorEnvio.set('No se pudo cargar PayPal. Inténtalo de nuevo en unos segundos.');
      this.mostrarPago.set(false);
    }
  }

  // Plan de prueba: sin pago.
  protected activarPrueba(): Promise<void> {
    return this.confirmar(null);
  }

  private async confirmar(orderId: string | null): Promise<void> {
    this.procesando.set(true);
    this.errorEnvio.set('');
    try {
      this.creada.set(await this.api.confirmar(this.solicitud(), orderId, this.logo()));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      this.errorEnvio.set(
        this.mensaje(err, 'No pudimos registrar tu boutique. Si se te cobró, escríbenos y lo resolvemos.'),
      );
    } finally {
      this.procesando.set(false);
    }
  }

  private salirDelPago(): void {
    this.mostrarPago.set(false);
    this.errorEnvio.set('');
  }

  // El administrador entra con su cuenta nueva: se cierra la sesión de cliente.
  protected async irAlPanel(): Promise<void> {
    await this.auth.logout();
    void this.router.navigate(['/login']);
  }

  private mensaje(err: unknown, porDefecto: string): string {
    if (err instanceof HttpErrorResponse) {
      const detalle = err.error?.detail;
      if (typeof detalle === 'string') return detalle;
      if (Array.isArray(detalle) && detalle[0]?.msg) return 'Revisa los datos: ' + detalle[0].msg;
    }
    return porDefecto;
  }

  private leerPlanInicial(): string {
    const pedido = this.route.snapshot.queryParamMap.get('plan');
    return PLANES.some((p) => p.id === pedido) ? pedido! : 'basico';
  }
}
