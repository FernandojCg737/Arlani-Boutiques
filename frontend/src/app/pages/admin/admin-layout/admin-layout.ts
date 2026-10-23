import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map, startWith } from 'rxjs/operators';
import { Auth } from '../../../services/auth';
import { EstadoTienda } from '../../../services/estado-tienda';
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
  private readonly estadoTienda = inject(EstadoTienda);

  // Suscripcion vencida (o tienda suspendida): solo "Mi suscripcion" queda
  // disponible; el resto del panel muestra el aviso.
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => this.router.url),
      startWith(this.router.url),
    ),
    { initialValue: this.router.url },
  );
  protected readonly bloqueada = computed(
    () => (this.estadoTienda.vencida() || !this.marca.operativa()) && !this.url().startsWith('/admin/suscripcion'),
  );

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
    return this.auth.isAdmin() || this.auth.hasPermiso(uc.permiso ?? uc.code) ? 'ok' : 'sin-acceso';
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
