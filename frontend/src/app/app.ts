import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ViewportScroller } from '@angular/common';
import { Component, DestroyRef, HostListener, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AvisoCompras } from './components/aviso-compras/aviso-compras';
import { ChatbotWidget } from './components/chatbot-widget/chatbot-widget';
import { Footer } from './components/footer/footer';
import { FooterPlataforma } from './components/footer-plataforma/footer-plataforma';
import { Header } from './components/header/header';
import { HeaderPlataforma } from './components/header-plataforma/header-plataforma';
import { LoginRequeridoModal } from './components/login-requerido/login-requerido';
import { WhatsappFloat } from './components/whatsapp-float/whatsapp-float';
import { Auth } from './services/auth';
import { InactivitySession } from './services/inactivity-session';
import { Sincronizacion } from './services/offline/sincronizacion';
import { TiendaActiva } from './services/tienda-activa';

@Component({
  imports: [
    RouterOutlet,
    Header,
    HeaderPlataforma,
    Footer,
    FooterPlataforma,
    WhatsappFloat,
    ChatbotWidget,
    LoginRequeridoModal,
    AvisoCompras,
  ],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly viewportScroller = inject(ViewportScroller);
  protected readonly auth = inject(Auth);
  protected readonly tiendaActiva = inject(TiendaActiva);
  // Se inyecta para que arranque: vigila inactividad (30 min) y valida la
  // sesion contra el backend mientras haya un usuario logueado.
  private readonly inactivitySession = inject(InactivitySession);
  // P4 offline: manda sola las operaciones guardadas sin conexion (CU12).
  private readonly sincronizacion = inject(Sincronizacion);

  // Paginas de auth (login/registro) usan su propia pantalla completa, sin
  // el header/footer del sitio: se marcan con data: { hideChrome: true }.
  protected readonly hideChrome = signal(false);
  // La portada (/) es de la plataforma Arlani Boutiques y usa su propio
  // encabezado; el resto de paginas de la tienda usan <app-header>. Se marca
  // con data: { header: 'plataforma' } en la ruta.
  protected readonly headerPlataforma = signal(false);
  // Páginas de la plataforma sin hero (data: { encabezadoSolido: true }):
  // el encabezado de Arlani va sólido desde arriba.
  protected readonly encabezadoSolido = signal(false);

  @HostListener('document:click')
  protected onDocumentClick(): void {
    if (this.auth.sessionMessage()) {
      this.auth.sessionMessage.set(null);
    }
  }

  ngOnInit(): void {
    // Los enlaces a secciones (#funciones, #boutiques...) las dejaban debajo
    // del encabezado fijo: el router calcula el scroll por su cuenta e ignora
    // scroll-margin-top, así que el alto del encabezado se descuenta acá.
    this.viewportScroller.setOffset([0, 84]);

    this.router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        let current = this.route.snapshot;
        while (current.firstChild) current = current.firstChild;
        this.hideChrome.set(!!current.data['hideChrome']);
        this.headerPlataforma.set(current.data['header'] === 'plataforma');
        // En las paginas de la plataforma no hay marca de tienda.
        if (current.data['header'] === 'plataforma') this.tiendaActiva.salir();
        this.encabezadoSolido.set(!!current.data['encabezadoSolido']);
      });
  }
}
