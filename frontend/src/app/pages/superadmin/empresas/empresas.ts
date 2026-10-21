import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import {
  EmpresaTenant,
  PeriodoSuscripcion,
  PlanPlataforma,
  PlataformaApi,
  enlaceDisponible,
  enlaceTiendaCorto,
  mensajeError,
  rutaTienda,
} from '../../../services/plataforma';
import { AvisosPanel } from '../avisos';

type Filtro = 'todas' | 'activas' | 'suspendidas' | 'prueba';
type Confirmacion = { tipo: 'suspender' | 'reactivar' | 'eliminar'; empresa: EmpresaTenant };

const CIUDADES = ['Santa Cruz', 'La Paz', 'Cochabamba', 'Sucre', 'Tarija', 'Oruro', 'Potosí', 'Trinidad', 'Cobija'];
const COLORES = ['#1f2a44', '#203c40', '#c4503d', '#6d2338', '#141414', '#a07d5a', '#3e4c6d', '#2f6b4f'];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function aSubdominio(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
}

// CU09 Gestionar empresas (tenants).
@Component({
  selector: 'app-superadmin-empresas',
  imports: [DecimalPipe, DatePipe],
  templateUrl: './empresas.html',
  styleUrl: './empresas.scss',
})
export class SuperadminEmpresas implements OnInit {
  private readonly api = inject(PlataformaApi);
  protected readonly rutaTienda = rutaTienda;
  // "arlani.onrender.com/tienda-" delante del campo del enlace.
  protected readonly prefijoEnlace = enlaceTiendaCorto();
  private readonly avisos = inject(AvisosPanel);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly ciudades = CIUDADES;
  protected readonly colores = COLORES;

  protected readonly cargando = signal(true);
  protected readonly empresas = signal<EmpresaTenant[]>([]);
  protected readonly planes = signal<PlanPlataforma[]>([]);
  protected readonly busqueda = signal('');
  protected readonly filtro = signal<Filtro>('todas');
  protected readonly ocupado = signal(false);

  // Panel lateral de alta / edición.
  protected readonly panel = signal<'nueva' | 'editar' | null>(null);
  protected readonly editando = signal<EmpresaTenant | null>(null);
  protected readonly intento = signal(false);
  protected readonly fNombre = signal('');
  protected readonly fSubdominio = signal('');
  private subdominioManual = false;
  // Enlace final de la empresa nueva (con numero si el escrito ya esta en uso).
  protected readonly enlaceFinal = enlaceDisponible(() => (this.panel() === 'nueva' ? this.fSubdominio() : ''));
  protected readonly enlaceOcupado = computed(
    () => this.panel() === 'nueva' && this.fSubdominio().length >= 3 && this.enlaceFinal() !== this.fSubdominio(),
  );
  protected readonly fCiudad = signal('Santa Cruz');
  protected readonly fEmail = signal('');
  protected readonly fColor = signal(COLORES[0]);
  protected readonly fPlan = signal('basico');
  protected readonly fPeriodo = signal<PeriodoSuscripcion>('mensual');

  // Cambio de plan y confirmaciones.
  protected readonly cambioPlan = signal<EmpresaTenant | null>(null);
  protected readonly cpPlan = signal('');
  protected readonly cpPeriodo = signal<PeriodoSuscripcion>('mensual');
  protected readonly confirmar = signal<Confirmacion | null>(null);

  protected readonly conteos = computed(() => {
    const l = this.empresas();
    return {
      todas: l.length,
      activas: l.filter((e) => e.estado === 'activa').length,
      suspendidas: l.filter((e) => e.estado === 'suspendida').length,
      prueba: l.filter((e) => e.periodo === 'prueba').length,
    };
  });

  protected readonly visibles = computed(() => {
    const q = this.busqueda().trim().toLowerCase();
    return this.empresas().filter((e) => {
      const pasaFiltro =
        this.filtro() === 'todas' ||
        (this.filtro() === 'activas' && e.estado === 'activa') ||
        (this.filtro() === 'suspendidas' && e.estado === 'suspendida') ||
        (this.filtro() === 'prueba' && e.periodo === 'prueba');
      const pasaTexto =
        !q || e.nombre.toLowerCase().includes(q) || e.subdominio.includes(q) || (e.ciudad ?? '').toLowerCase().includes(q);
      return pasaFiltro && pasaTexto;
    });
  });

  protected readonly errores = computed(() => {
    const e: Record<string, string> = {};
    if (this.fNombre().trim().length < 2) e['nombre'] = 'Escribe el nombre de la empresa.';
    if (this.panel() === 'nueva' && !/^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$/.test(this.fSubdominio()))
      e['subdominio'] = 'Entre 3 y 40 letras, números o guiones.';
    if (this.fEmail().trim() && !EMAIL.test(this.fEmail().trim())) e['email'] = 'Correo no válido.';
    return e;
  });

  protected readonly planElegido = computed(() => this.planes().find((p) => p.codigo === this.fPlan()));

  protected readonly planCambio = computed(() => this.planes().find((p) => p.codigo === this.cpPlan()));

  async ngOnInit(): Promise<void> {
    await this.cargar();
    // Accesos directos desde el panel general (?nueva=1 o ?ver=<id>).
    const q = this.route.snapshot.queryParamMap;
    if (q.get('nueva')) this.abrirNueva();
    const ver = Number(q.get('ver'));
    if (ver) {
      const empresa = this.empresas().find((e) => e.id === ver);
      if (empresa) this.abrirEditar(empresa);
    }
  }

  @HostListener('document:keydown.escape')
  protected alEscape(): void {
    this.cerrarPanel();
    this.cambioPlan.set(null);
    this.confirmar.set(null);
  }

  private async cargar(): Promise<void> {
    try {
      const [empresas, planes] = await Promise.all([this.api.empresas(), this.api.planes()]);
      this.empresas.set(empresas);
      this.planes.set(planes);
    } catch (err) {
      this.avisos.error(mensajeError(err, 'No pudimos cargar las empresas.'));
    } finally {
      this.cargando.set(false);
    }
  }

  private reemplazar(empresa: EmpresaTenant): void {
    this.empresas.update((l) => {
      const i = l.findIndex((e) => e.id === empresa.id);
      return i === -1 ? [...l, empresa] : l.map((e) => (e.id === empresa.id ? empresa : e));
    });
  }

  // ---------------------------------------------------------- alta / edición
  protected abrirNueva(): void {
    this.editando.set(null);
    this.fNombre.set('');
    this.fSubdominio.set('');
    this.subdominioManual = false;
    this.fCiudad.set('Santa Cruz');
    this.fEmail.set('');
    this.fColor.set(COLORES[0]);
    this.fPlan.set('basico');
    this.fPeriodo.set('mensual');
    this.intento.set(false);
    this.panel.set('nueva');
  }

  protected abrirEditar(e: EmpresaTenant): void {
    this.editando.set(e);
    this.fNombre.set(e.nombre);
    this.fSubdominio.set(e.subdominio);
    this.fCiudad.set(e.ciudad ?? 'Santa Cruz');
    this.fEmail.set(e.emailContacto ?? '');
    this.fColor.set(e.colorMarca);
    this.intento.set(false);
    this.panel.set('editar');
  }

  protected cerrarPanel(): void {
    this.panel.set(null);
    // Limpia ?nueva / ?ver de la URL para que recargar no reabra el panel.
    if (this.route.snapshot.queryParamMap.keys.length) {
      void this.router.navigate([], { queryParams: {}, replaceUrl: true });
    }
  }

  protected alCambiarNombre(v: string): void {
    this.fNombre.set(v);
    if (this.panel() === 'nueva' && !this.subdominioManual) this.fSubdominio.set(aSubdominio(v));
  }

  protected alCambiarSubdominio(v: string): void {
    this.subdominioManual = true;
    this.fSubdominio.set(aSubdominio(v));
  }

  protected error(campo: string): string | null {
    return this.intento() ? (this.errores()[campo] ?? null) : null;
  }

  protected async guardar(): Promise<void> {
    if (Object.keys(this.errores()).length) {
      this.intento.set(true);
      return;
    }
    this.ocupado.set(true);
    try {
      const datos = {
        nombre: this.fNombre().trim(),
        ciudad: this.fCiudad(),
        color_marca: this.fColor(),
        email_contacto: this.fEmail().trim() || null,
      };
      const editando = this.editando();
      if (editando) {
        this.reemplazar(await this.api.actualizarEmpresa(editando.id, datos));
        this.avisos.exito(`Se guardaron los cambios de ${datos.nombre}.`);
      } else {
        const nueva = await this.api.crearEmpresa({
          ...datos,
          subdominio: this.fSubdominio(),
          plan_codigo: this.fPlan(),
          periodo: this.fPeriodo(),
        });
        this.reemplazar(nueva);
        this.avisos.exito(`${nueva.nombre} ya es parte de Arlani.`);
      }
      this.cerrarPanel();
    } catch (err) {
      this.avisos.error(mensajeError(err));
    } finally {
      this.ocupado.set(false);
    }
  }

  // ------------------------------------------------------------ cambio de plan
  protected abrirCambioPlan(e: EmpresaTenant): void {
    this.cambioPlan.set(e);
    this.cpPlan.set(e.planCodigo ?? 'basico');
    this.cpPeriodo.set(e.periodo === 'anual' ? 'anual' : 'mensual');
  }

  protected cubre(plan: PlanPlataforma, e: EmpresaTenant): boolean {
    return e.sucursalesActivas <= plan.maxSucursales;
  }

  protected async confirmarCambioPlan(): Promise<void> {
    const e = this.cambioPlan();
    if (!e) return;
    this.ocupado.set(true);
    try {
      const actualizada = await this.api.cambiarPlan(e.id, this.cpPlan(), this.cpPeriodo());
      this.reemplazar(actualizada);
      this.avisos.exito(`${e.nombre} ahora tiene el plan ${actualizada.planNombre}.`);
      this.cambioPlan.set(null);
    } catch (err) {
      this.avisos.error(mensajeError(err));
    } finally {
      this.ocupado.set(false);
    }
  }

  // -------------------------------------------- suspender / reactivar / borrar
  protected async ejecutarConfirmacion(): Promise<void> {
    const c = this.confirmar();
    if (!c) return;
    this.ocupado.set(true);
    try {
      if (c.tipo === 'eliminar') {
        await this.api.eliminarEmpresa(c.empresa.id);
        this.empresas.update((l) => l.filter((e) => e.id !== c.empresa.id));
        this.avisos.exito(`${c.empresa.nombre} se eliminó de la plataforma.`);
      } else {
        const estado = c.tipo === 'suspender' ? 'suspendida' : 'activa';
        this.reemplazar(await this.api.cambiarEstado(c.empresa.id, estado));
        this.avisos.exito(`${c.empresa.nombre} quedó ${estado === 'activa' ? 'reactivada' : 'suspendida'}.`);
      }
      this.confirmar.set(null);
    } catch (err) {
      this.avisos.error(mensajeError(err));
    } finally {
      this.ocupado.set(false);
    }
  }

  // ------------------------------------------------------------------ apoyo
  protected usoPct(e: EmpresaTenant): number {
    return e.maxSucursales ? Math.min(100, Math.round((e.sucursalesActivas / e.maxSucursales) * 100)) : 0;
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  protected periodoTexto(p: PeriodoSuscripcion | null): string {
    return p === 'anual' ? 'Anual' : p === 'prueba' ? 'Gratis' : 'Mensual';
  }
}
