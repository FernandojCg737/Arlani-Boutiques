import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  OnDestroy,
  OnInit,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Auth } from '../../services/auth';
import { Cart } from '../../services/cart';
import { LoginRequerido } from '../../services/login-requerido';
import { Notificaciones, type Notificacion } from '../../services/notificaciones';

const INTERVALO_NOTIFICACIONES_MS = 30000;

interface NavLink {
  label: string;
  path: string;
  queryParams?: Record<string, string>;
}

@Component({
  selector: 'app-header',
  imports: [RouterLink, DatePipe],
  templateUrl: './header.html',
  styleUrl: './header.scss',
})
export class Header implements OnInit, OnDestroy {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly cart = inject(Cart);
  protected readonly auth = inject(Auth);
  protected readonly notificaciones = inject(Notificaciones);
  private readonly loginRequerido = inject(LoginRequerido);

  // Paginas sin ".hero" (fondo oscuro a pantalla completa) no tienen contra
  // que contrastar un header transparente: quedaria blanco sobre blanco. En
  // esas paginas el header se muestra siempre solido, sin importar el scroll.
  private hasHero = true;

  protected readonly scrolled = signal(false);
  protected readonly mobileMenuOpen = signal(false);
  protected readonly searchOpen = signal(false);
  protected readonly searchQuery = signal('');
  protected readonly accountMenuOpen = signal(false);
  protected readonly notifMenuOpen = signal(false);

  private readonly searchInput = viewChild<ElementRef<HTMLInputElement>>('searchInput');
  private intervaloNotificaciones?: ReturnType<typeof setInterval>;

  protected readonly esClienteConSesion = () => !!this.auth.currentUser() && !this.auth.isStaff();

  constructor() {
    // El carrito y las notificaciones viven en el backend ligados al
    // cliente: se recargan cada vez que cambia la sesion (login/logout)
    // para que el badge y las paginas siempre reflejen al usuario actual.
    // Las notificaciones ademas hacen polling mientras haya sesion de
    // cliente, para que la campana se sienta "en vivo".
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
    if (this.intervaloNotificaciones) clearInterval(this.intervaloNotificaciones);
  }

  protected readonly navLinks: NavLink[] = [
    { label: 'Tienda', path: '/tienda' },
    { label: 'Poleras', path: '/tienda', queryParams: { categoria: 'poleras' } },
    { label: 'Pantalones', path: '/tienda', queryParams: { categoria: 'pantalones' } },
    { label: 'Ofertas', path: '/tienda', queryParams: { filtro: 'ofertas' } },
    { label: 'Cotizaciones', path: '/cotizaciones' },
    { label: 'Contacto', path: '/contacto' },
  ];

  ngOnInit(): void {
    this.refreshForCurrentRoute();

    this.router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        // El componente de la nueva ruta recien se pinta despues de este
        // evento; se espera un tick para que ".hero" ya exista en el DOM.
        setTimeout(() => this.refreshForCurrentRoute());
        this.closeSearch();
        this.accountMenuOpen.set(false);
        this.notifMenuOpen.set(false);
      });
  }

  @HostListener('document:click', ['$event'])
  protected onDocumentClick(event: MouseEvent): void {
    const target = event.target as HTMLElement;
    if (this.accountMenuOpen() && !target.closest('.account-menu-wrap')) {
      this.accountMenuOpen.set(false);
    }
    if (this.notifMenuOpen() && !target.closest('.notif-menu-wrap')) {
      this.notifMenuOpen.set(false);
    }
  }

  protected toggleAccountMenu(): void {
    this.accountMenuOpen.update((open) => !open);
  }

  protected toggleNotifMenu(): void {
    this.notifMenuOpen.update((open) => !open);
    if (this.notifMenuOpen()) void this.notificaciones.cargar();
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

  // El icono del carrito se ve siempre; sin sesion, en vez de abrir un
  // carrito vacio, avisa que hay que iniciar sesion.
  protected abrirCarrito(event: Event): void {
    this.closeMobileMenu();
    if (this.auth.currentUser()) return;
    event.preventDefault();
    this.loginRequerido.pedir('para ver tu carrito de compras', '/carrito');
  }

  protected async logout(): Promise<void> {
    await this.auth.logout();
    this.accountMenuOpen.set(false);
    this.router.navigateByUrl('/');
  }

  private refreshForCurrentRoute(): void {
    this.hasHero = !!document.querySelector('.hero');
    this.onWindowScroll();
  }

  @HostListener('window:scroll')
  protected onWindowScroll(): void {
    this.scrolled.set(!this.hasHero || window.scrollY > 40);
  }

  protected toggleMobileMenu(): void {
    this.mobileMenuOpen.update((open) => !open);
  }

  protected closeMobileMenu(): void {
    this.mobileMenuOpen.set(false);
  }

  protected toggleSearch(): void {
    this.searchOpen.update((open) => !open);
    if (this.searchOpen()) {
      // Esperar a que el input este en el DOM (fuera del @if) antes de enfocarlo.
      setTimeout(() => this.searchInput()?.nativeElement.focus());
    }
  }

  protected closeSearch(): void {
    this.searchOpen.set(false);
    this.searchQuery.set('');
  }

  // TODO: cuando exista el endpoint real de busqueda en el backend (tabla
  // Producto), este query param "buscar" ya queda listo para consumirse ahi
  // mismo. Por ahora ProductGrid filtra el catalogo de prueba por nombre.
  protected submitSearch(): void {
    const termino = this.searchQuery().trim();
    if (!termino) return;

    this.router.navigate(['/tienda'], { queryParams: { buscar: termino } });
    this.closeSearch();
  }
}
