import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Auth } from '../../../services/auth';
import { MarcaTienda } from '../../../services/marca-tienda';
import { ADMIN_MENU, AdminUseCase } from '../admin-menu';

// CU15 (Actualizar Perfil de Usuario) es autoservicio: cualquier personal
// autenticado puede editar su propio perfil, sin pasar por la matriz de
// permisos de CU02.
const SIEMPRE_PERMITIDO = new Set(['CU15']);

@Component({
  selector: 'app-admin-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './admin-layout.html',
  styleUrl: './admin-layout.scss',
})
export class AdminLayout {
  protected readonly auth = inject(Auth);
  // Logo, nombre y color de la tienda del usuario (no los de Atelier fijos).
  protected readonly marca = inject(MarcaTienda);
  private readonly router = inject(Router);

  constructor() {
    void this.marca.cargar();
  }

  protected readonly menu = ADMIN_MENU;
  protected readonly openPackage = signal<string | null>(null);
  protected readonly activePackage = computed(
    () => this.menu.find((pkg) => pkg.code === this.openPackage()) ?? null,
  );

  protected estadoUseCase(uc: AdminUseCase): 'ok' | 'sin-acceso' | 'proximamente' {
    if (!uc.route) return 'proximamente';
    if (SIEMPRE_PERMITIDO.has(uc.code)) return 'ok';
    return this.auth.isAdmin() || this.auth.hasPermiso(uc.code) ? 'ok' : 'sin-acceso';
  }

  protected togglePackage(code: string): void {
    this.openPackage.update((current) => (current === code ? null : code));
  }

  @HostListener('document:click', ['$event'])
  protected onDocumentClick(event: MouseEvent): void {
    if (!this.openPackage()) return;
    const target = event.target as HTMLElement;
    if (!target.closest('.pkg-tile') && !target.closest('.pkg-panel')) {
      this.openPackage.set(null);
    }
  }

  protected async logout(): Promise<void> {
    await this.auth.logout();
    this.router.navigateByUrl('/login');
  }
}
