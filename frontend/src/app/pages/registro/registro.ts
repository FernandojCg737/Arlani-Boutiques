import { HttpErrorResponse } from '@angular/common/http';
import { AfterViewInit, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AuthShowcase } from '../../components/auth-showcase/auth-showcase';
import { Auth } from '../../services/auth';
import { GoogleIdentity } from '../../services/google-identity';
import { esRutaInterna } from '../../services/login-requerido';
import { checkPassword, isPasswordValid } from '../../utils/password';

@Component({
  selector: 'app-registro',
  imports: [RouterLink, AuthShowcase],
  templateUrl: './registro.html',
  styleUrl: './registro.scss',
})
export class Registro implements AfterViewInit {
  private readonly auth = inject(Auth);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly googleIdentity = inject(GoogleIdentity);

  protected readonly nombre = signal('');
  protected readonly email = signal('');
  protected readonly telefono = signal('');
  protected readonly password = signal('');
  protected readonly confirmPassword = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly showPassword = signal(false);
  protected readonly showConfirmPassword = signal(false);
  protected readonly passwordTouched = signal(false);
  protected readonly passwordChecks = computed(() => checkPassword(this.password()));
  protected readonly returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');

  ngAfterViewInit(): void {
    this.googleIdentity.renderButton('googleBtnRegistro', (credential) => this.handleGoogleCredential(credential));
  }

  protected async submit(): Promise<void> {
    this.passwordTouched.set(true);

    if (!this.nombre() || !this.email() || !this.password()) {
      this.error.set('Completa nombre, correo y contrasena.');
      return;
    }

    if (!isPasswordValid(this.password())) {
      this.error.set('La contrasena no cumple los requisitos minimos.');
      return;
    }

    if (this.password() !== this.confirmPassword()) {
      this.error.set('Las contrasenas no coinciden.');
      return;
    }

    this.error.set('');
    this.loading.set(true);
    try {
      await this.auth.register({
        nombre: this.nombre(),
        email: this.email(),
        password: this.password(),
        telefono: this.telefono() || undefined,
      });
      this.irDespuesDeEntrar();
    } catch (err) {
      this.error.set(this.extractError(err));
    } finally {
      this.loading.set(false);
    }
  }

  // Igual que login: si llego aca desde "inicia sesion para anadir al
  // carrito/reservar/probarte", vuelve a esa accion en vez de al inicio.
  private irDespuesDeEntrar(): void {
    const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
    this.router.navigateByUrl(esRutaInterna(returnUrl) ? returnUrl : '/');
  }

  private async handleGoogleCredential(credential: string): Promise<void> {
    this.error.set('');
    this.loading.set(true);
    try {
      await this.auth.loginWithGoogle(credential);
      this.irDespuesDeEntrar();
    } catch (err) {
      this.error.set(this.extractError(err));
    } finally {
      this.loading.set(false);
    }
  }

  private extractError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
      if (err.status === 0) return 'No pudimos conectar con el servidor. Intenta de nuevo.';
    }
    return 'Ocurrio un error inesperado. Intenta de nuevo.';
  }
}
