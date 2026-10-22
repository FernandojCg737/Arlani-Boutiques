import { HttpErrorResponse } from '@angular/common/http';
import { AfterViewInit, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthShowcase } from '../../components/auth-showcase/auth-showcase';
import { Auth } from '../../services/auth';
import { GoogleIdentity } from '../../services/google-identity';
import { MarcaTienda } from '../../services/marca-tienda';
import { esRutaInterna } from '../../services/login-requerido';

@Component({
  selector: 'app-login',
  imports: [RouterLink, AuthShowcase],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login implements AfterViewInit {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly googleIdentity = inject(GoogleIdentity);
  private readonly marca = inject(MarcaTienda);

  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly showPassword = signal(false);

  ngAfterViewInit(): void {
    this.googleIdentity.renderButton('googleBtnLogin', (credential) => this.handleGoogleCredential(credential));
  }

  protected async submit(): Promise<void> {
    if (!this.email() || !this.password()) {
      this.error.set('Completa tu correo y contrasena.');
      return;
    }

    this.error.set('');
    this.loading.set(true);
    try {
      await this.auth.login({ email: this.email(), password: this.password() });
      await this.redirectAfterLogin();
    } catch (err) {
      this.error.set(this.extractError(err));
    } finally {
      this.loading.set(false);
    }
  }

  private async handleGoogleCredential(credential: string): Promise<void> {
    this.error.set('');
    this.loading.set(true);
    try {
      await this.auth.loginWithGoogle(credential);
      await this.redirectAfterLogin();
    } catch (err) {
      this.error.set(this.extractError(err));
    } finally {
      this.loading.set(false);
    }
  }

  private async redirectAfterLogin(): Promise<void> {
    // Personal de una tienda: su marca llega antes de abrir el panel, asi
    // entra ya con su logo y su color (sin pasar por otros colores).
    const tipo = this.auth.currentUser()?.tipo;
    if (tipo === 'administrador' || tipo === 'encargado_sucursal' || tipo === 'cajero') await this.marca.cargar();
    // `returnUrl` viene de authGuard (rutas protegidas, ej. /checkout) o de
    // acciones que mandaron aca por falta de sesion (agregar al carrito,
    // reservar, probarse una prenda desde la ficha de producto) -- si esta
    // presente, volvemos justo ahi en vez de al landing por defecto. Se
    // valida que sea una ruta interna (empiece con "/") para no abrir una
    // URL externa arbitraria.
    const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
    this.router.navigateByUrl(esRutaInterna(returnUrl) ? returnUrl : this.auth.landingRoute());
  }

  // Se pasa el mismo returnUrl a /registro: si el visitante no tenia cuenta,
  // al registrarse tambien vuelve a la accion que estaba intentando.
  protected readonly returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');

  private extractError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor. Intenta de nuevo.';
    }
    return 'Ocurrio un error inesperado. Intenta de nuevo.';
  }
}
