import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map, startWith } from 'rxjs/operators';
import { Auth } from '../../services/auth';
import { EmpresaTenant, PlataformaApi } from '../../services/plataforma';
import { AvisosPanel } from './avisos';
import {
  CasoUsoMenu,
  PARCIALES,
  PaqueteMenu,
  ParcialId,
  UbicacionCu,
  buscarCaso,
  ubicarRuta,
} from './superadmin-menu';

// Panel del SuperAdministrador: mismo esquema que el panel de una tienda
// (barra superior + cuadros de paquetes), con un nivel más arriba para
// elegir el parcial. Entra directo a la bitácora (CU08).
@Component({
  selector: 'app-superadmin-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './superadmin-layout.html',
  styleUrl: './superadmin-layout.scss',
})
export class SuperadminLayout {
  protected readonly auth = inject(Auth);
  protected readonly avisos = inject(AvisosPanel);
  private readonly router = inject(Router);
  private readonly api = inject(PlataformaApi);

  protected readonly parciales = PARCIALES;

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => this.router.url),
      startWith(this.router.url),
    ),
    { initialValue: this.router.url },
  );

  // Dónde estamos: parcial, paquete y CU de la pantalla abierta.
  protected readonly ubicacion = computed<UbicacionCu | null>(() => {
    const arbol = this.router.parseUrl(this.url());
    const segs = arbol.root.children['primary']?.segments.map((s) => s.path) ?? [];
    const [, seccion, extra] = segs;
    if (seccion === 'cu' && extra) return buscarCaso('p2', extra);
    if (seccion === 'empresa' && extra) return buscarCaso('p1', extra);
    return seccion ? ubicarRuta(seccion) : null;
  });

  protected readonly empresaId = computed(() => {
    const id = Number(this.router.parseUrl(this.url()).queryParamMap.get('empresa'));
    return Number.isFinite(id) && id > 0 ? id : null;
  });

  private readonly empresas = signal<EmpresaTenant[]>([]);
  protected readonly empresaActual = computed(() => this.empresas().find((e) => e.id === this.empresaId()) ?? null);

  protected readonly parcialActivo = signal<ParcialId>('p2');
  protected readonly paqueteAbierto = signal<string | null>(null);

  protected readonly paquetes = computed(
    () => PARCIALES.find((p) => p.id === this.parcialActivo())?.paquetes ?? [],
  );
  protected readonly paquete = computed<PaqueteMenu | null>(
    () => this.paquetes().find((p) => p.codigo === this.paqueteAbierto()) ?? null,
  );

  constructor() {
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {
      this.paqueteAbierto.set(null);
      // El parcial seleccionado sigue a la pantalla abierta.
      const u = this.ubicacion();
      if (u) this.parcialActivo.set(u.parcial.id);
      if (this.empresaId() && this.empresas().length === 0) void this.cargarEmpresas();
    });
    const u = this.ubicacion();
    if (u) this.parcialActivo.set(u.parcial.id);
    if (this.empresaId()) void this.cargarEmpresas();
  }

  private async cargarEmpresas(): Promise<void> {
    try {
      this.empresas.set(await this.api.empresas());
    } catch {
      // Sin la lista solo se pierde el nombre en la franja de contexto.
    }
  }

  protected elegirParcial(id: ParcialId): void {
    this.paqueteAbierto.set(this.parcialActivo() === id ? this.paqueteAbierto() : null);
    this.parcialActivo.set(id);
  }

  protected alternarPaquete(codigo: string): void {
    this.paqueteAbierto.update((actual) => (actual === codigo ? null : codigo));
  }

  // A dónde lleva un CU del menú.
  protected destino(caso: CasoUsoMenu): string[] {
    if (this.parcialActivo() === 'p1' && caso.porEmpresa) return ['/superadmin/empresa', caso.codigo];
    if (!caso.ruta) return ['/superadmin/cu', caso.codigo];
    return ['/superadmin', caso.ruta];
  }

  protected esActual(caso: CasoUsoMenu): boolean {
    return this.ubicacion()?.caso.codigo === caso.codigo && this.ubicacion()?.parcial.id === this.parcialActivo();
  }

  // Ir a un CU que pasó al 2do parcial desde la lista "movidos" del 1ro.
  protected irAlSegundo(codigo: string): void {
    const u = buscarCaso('p2', codigo);
    if (!u) return;
    void this.router.navigate(u.caso.ruta ? ['/superadmin', u.caso.ruta] : ['/superadmin/cu', codigo]);
  }

  @HostListener('document:click', ['$event'])
  protected alClickFuera(evento: MouseEvent): void {
    if (!this.paqueteAbierto()) return;
    const t = evento.target as HTMLElement;
    if (!t.closest('.paquete') && !t.closest('.desplegable')) this.paqueteAbierto.set(null);
  }

  @HostListener('document:keydown.escape')
  protected alEscape(): void {
    this.paqueteAbierto.set(null);
  }

  protected async cerrarSesion(): Promise<void> {
    await this.auth.logout();
    void this.router.navigateByUrl('/login');
  }
}
