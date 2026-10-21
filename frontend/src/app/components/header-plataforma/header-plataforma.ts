import { DatePipe } from '@angular/common';
import {
  Component,
  ElementRef,
  HostListener,
  OnDestroy,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Auth } from '../../services/auth';
import { Cart } from '../../services/cart';
import { LoginRequerido } from '../../services/login-requerido';
import { Notificaciones, type Notificacion } from '../../services/notificaciones';

interface ItemMenu {
  titulo: string;
  detalle: string;
  fragmento: string;
}

interface ColumnaMenu {
  titulo: string;
  items: ItemMenu[];
}

type MenuId = 'por-que' | 'funciones';

const INTERVALO_NOTIFICACIONES_MS = 30000;

// Encabezado de la portada de Arlani Boutiques (la plataforma SaaS). Va sobre
// el video del hero, transparente, y pasa a vidrio translúcido al hacer
// scroll. Mantiene las mismas acciones del encabezado de la tienda (buscar,
// notificaciones, cuenta y carrito). La tienda de Atelier Aranier (/tienda,
// producto, carrito...) sigue usando su propio <app-header>; ver app.ts.
@Component({
  selector: 'app-header-plataforma',
  imports: [RouterLink, DatePipe],
  templateUrl: './header-plataforma.html',
  styleUrl: './header-plataforma.scss',
})
export class HeaderPlataforma implements OnDestroy {
  protected readonly auth = inject(Auth);
  protected readonly cart = inject(Cart);
  protected readonly notificaciones = inject(Notificaciones);
  private readonly loginRequerido = inject(LoginRequerido);
  private readonly router = inject(Router);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  // En páginas sin hero (carrito, etc.) no hay foto oscura detrás: la barra
  // va azul noche sólida desde arriba para que el texto blanco se lea.
  readonly siempreSolido = input(false);

  protected readonly solido = signal(false);
  protected readonly menuAbierto = signal<MenuId | null>(null);
  protected readonly menuMovilAbierto = signal(false);
  protected readonly cuentaAbierta = signal(false);
  protected readonly notifAbiertas = signal(false);
  protected readonly buscando = signal(false);
  protected readonly busqueda = signal('');
  private cierreDiferido?: ReturnType<typeof setTimeout>;
  private intervaloNotificaciones?: ReturnType<typeof setInterval>;
  private readonly campoBusqueda = viewChild<ElementRef<HTMLInputElement>>('campoBusqueda');

  protected readonly esClienteConSesion = () => !!this.auth.currentUser() && !this.auth.isStaff();

  // Las secciones de la portada (#por-que, #funciones, #precios) se arman en
  // los próximos pasos; los enlaces ya apuntan a ellas.
  protected readonly porQue: ItemMenu[] = [
    { titulo: 'Boutiques que recién empiezan', detalle: 'Tu tienda online con tu marca, lista para vender.', fragmento: 'por-que' },
    { titulo: 'Cadenas con varias sucursales', detalle: 'Stock, ventas y personal de cada sucursal en un panel.', fragmento: 'por-que' },
    { titulo: 'Tiendas con mala señal', detalle: 'Vendé y reservá aunque se caiga internet.', fragmento: 'por-que' },
  ];

  protected readonly funciones: ColumnaMenu[] = [
    {
      titulo: 'Vender',
      items: [
        { titulo: 'Tienda online', detalle: 'Catálogo con tu logo y tus colores.', fragmento: 'funciones' },
        { titulo: 'Ventas en línea y en mostrador', detalle: 'PayPal, QR y efectivo en un solo lugar.', fragmento: 'funciones' },
        { titulo: 'Reservas', detalle: 'El cliente aparta y paga al retirar.', fragmento: 'funciones' },
      ],
    },
    {
      titulo: 'Operar',
      items: [
        { titulo: 'Inventario por sucursal', detalle: 'Cuánto queda de cada talla y color.', fragmento: 'funciones' },
        { titulo: 'Ventas sin internet', detalle: 'Se guardan y se sincronizan solas.', fragmento: 'funciones' },
        { titulo: 'Empleados y permisos', detalle: 'Cada cajero ve solo lo suyo.', fragmento: 'funciones' },
      ],
    },
    {
      titulo: 'Crecer',
      items: [
        { titulo: 'Reportes con IA', detalle: 'Preguntá en tus palabras, recibí el reporte.', fragmento: 'funciones' },
        { titulo: 'Probador virtual', detalle: 'Realidad aumentada antes de comprar.', fragmento: 'funciones' },
        { titulo: 'Recomendaciones', detalle: 'Sugerencias según lo que mira cada cliente.', fragmento: 'funciones' },
      ],
    },
  ];

  constructor() {
    // Igual que <app-header>: el carrito y las notificaciones viven en el
    // backend ligados al cliente; se recargan cuando cambia la sesión, y las
    // notificaciones hacen polling mientras haya un cliente logueado.
    effect(() => {
      if (this.auth.currentUser()) {
        void this.cart.cargar();
      } else {
        this.cart.limpiarLocal();
      }

      if (this.esClienteConSesion()) {
        void this.notificaciones.cargar();
        if (!this.intervaloNotificaciones) {
          this.intervaloNotificaciones = setInterval(() => void this.notificaciones.cargar(), INTERVALO_NOTIFICACIONES_MS);
        }
      } else {
        this.notificaciones.limpiarLocal();
        if (this.intervaloNotificaciones) {
          clearInterval(this.intervaloNotificaciones);
          this.intervaloNotificaciones = undefined;
        }
      }
    });
  }

  ngOnDestroy(): void {
    clearInterval(this.intervaloNotificaciones);
    clearTimeout(this.cierreDiferido);
  }

  @HostListener('window:scroll')
  protected alScroll(): void {
    this.solido.set(window.scrollY > 24);
  }

  @HostListener('document:keydown.escape')
  protected alEscape(): void {
    this.cerrarTodo();
    this.cerrarBusqueda();
  }

  @HostListener('document:click', ['$event'])
  protected alClickFuera(evento: MouseEvent): void {
    const objetivo = evento.target as HTMLElement;
    if (!this.host.nativeElement.contains(objetivo)) this.menuAbierto.set(null);
    if (this.cuentaAbierta() && !objetivo.closest('.cuenta')) this.cuentaAbierta.set(false);
    if (this.notifAbiertas() && !objetivo.closest('.notif')) this.notifAbiertas.set(false);
  }

  // ---------------------------------------------------- menús desplegables
  // En escritorio se abren al pasar el cursor; el cierre espera un instante
  // para que se pueda cruzar del botón al panel sin que se cierre.
  protected abrirConCursor(id: MenuId): void {
    clearTimeout(this.cierreDiferido);
    this.menuAbierto.set(id);
  }

  protected cerrarConCursor(): void {
    clearTimeout(this.cierreDiferido);
    this.cierreDiferido = setTimeout(() => this.menuAbierto.set(null), 160);
  }

  protected alternar(id: MenuId): void {
    this.menuAbierto.update((actual) => (actual === id ? null : id));
  }

  protected cerrarTodo(): void {
    this.menuAbierto.set(null);
    this.menuMovilAbierto.set(false);
    this.cuentaAbierta.set(false);
    this.notifAbiertas.set(false);
  }

  // --------------------------------------------------------------- buscar
  protected abrirBusqueda(): void {
    this.buscando.set(true);
    // Esperar a que el campo exista en el DOM antes de enfocarlo.
    setTimeout(() => this.campoBusqueda()?.nativeElement.focus());
  }

  protected cerrarBusqueda(): void {
    this.buscando.set(false);
    this.busqueda.set('');
  }

  protected buscar(): void {
    const termino = this.busqueda().trim();
    if (!termino) return;
    void this.router.navigate(['/tienda-atelier-aranier'], { queryParams: { buscar: termino } });
    this.cerrarBusqueda();
    this.cerrarTodo();
  }

  // ------------------------------------------------- cuenta y notificaciones
  protected alternarCuenta(): void {
    this.cuentaAbierta.update((v) => !v);
    this.notifAbiertas.set(false);
  }

  protected alternarNotif(): void {
    this.notifAbiertas.update((v) => !v);
    this.cuentaAbierta.set(false);
    if (this.notifAbiertas()) void this.notificaciones.cargar();
  }

  protected marcarNotifLeida(id: number): void {
    void this.notificaciones.marcarLeida(id);
  }

  protected marcarTodasNotifLeidas(): void {
    void this.notificaciones.marcarTodasLeidas();
  }

  protected enlaceNotif(n: Notificacion): unknown[] {
    if (n.entidad_tipo === 'venta' && n.entidad_id) return ['/mis-compras', n.entidad_id];
    return ['/perfil'];
  }

  protected async cerrarSesion(): Promise<void> {
    await this.auth.logout();
    this.cerrarTodo();
    void this.router.navigateByUrl('/');
  }

  // --------------------------------------------------------------- carrito
  // El icono del carrito se ve siempre; sin sesión, en vez de abrir un
  // carrito vacío, avisa que hay que iniciar sesión (igual que <app-header>).
  protected abrirCarrito(evento: Event): void {
    this.cerrarTodo();
    if (this.auth.currentUser()) return;
    evento.preventDefault();
    this.loginRequerido.pedir('para ver tu carrito de compras', '/carrito');
  }
}
