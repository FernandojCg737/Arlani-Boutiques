import { Component, HostListener, inject } from '@angular/core';
import { Router } from '@angular/router';
import { LoginRequerido } from '../../services/login-requerido';

@Component({
  selector: 'app-login-requerido',
  templateUrl: './login-requerido.html',
  styleUrl: './login-requerido.scss',
})
export class LoginRequeridoModal {
  protected readonly loginRequerido = inject(LoginRequerido);
  private readonly router = inject(Router);

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    this.loginRequerido.cerrar();
  }

  protected ir(ruta: '/login' | '/registro'): void {
    const pedido = this.loginRequerido.pedido();
    this.loginRequerido.cerrar();
    void this.router.navigate([ruta], { queryParams: pedido ? { returnUrl: pedido.returnUrl } : {} });
  }
}
