import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Component, DestroyRef, HostListener, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';
import { ChatbotWidget } from './components/chatbot-widget/chatbot-widget';
import { Footer } from './components/footer/footer';
import { Header } from './components/header/header';
import { LoginRequeridoModal } from './components/login-requerido/login-requerido';
import { WhatsappFloat } from './components/whatsapp-float/whatsapp-float';
import { Auth } from './services/auth';
import { InactivitySession } from './services/inactivity-session';

@Component({
  imports: [RouterOutlet, Header, Footer, WhatsappFloat, ChatbotWidget, LoginRequeridoModal],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(Auth);
  // Se inyecta para que arranque: vigila inactividad (30 min) y valida la
  // sesion contra el backend mientras haya un usuario logueado.
  private readonly inactivitySession = inject(InactivitySession);

  // Paginas de auth (login/registro) usan su propia pantalla completa, sin
  // el header/footer del sitio: se marcan con data: { hideChrome: true }.
  protected readonly hideChrome = signal(false);

  @HostListener('document:click')
  protected onDocumentClick(): void {
    if (this.auth.sessionMessage()) {
      this.auth.sessionMessage.set(null);
    }
  }

  ngOnInit(): void {
    this.router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        let current = this.route.snapshot;
        while (current.firstChild) current = current.firstChild;
        this.hideChrome.set(!!current.data['hideChrome']);
      });
  }
}
