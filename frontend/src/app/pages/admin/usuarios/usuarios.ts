import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import { EmpresaTenant, PlataformaApi } from '../../../services/plataforma';
import { CasoUsoMenu, PARCIALES, permisosDe } from '../../superadmin/superadmin-menu';
import { ADMIN_MENU } from '../admin-menu';

interface Sucursal {
  id: number;
  nombre: string;
  empresa_id: number | null;
}

interface Rol {
  id: number;
  nombre: string;
  descripcion: string | null;
  permisos: string[];
}

interface Permiso {
  id: number;
  nombre: string;
  descripcion: string | null;
}

interface Empleado {
  id: number;
  nombre: string;
  email: string;
  tipo: string;
  estado: string;
  fecha_registro: string;
  metodo_registro: string;
  sucursal_id: number | null;
  sucursal_nombre: string | null;
  rol_id: number | null;
  rol_nombre: string | null;
  empresa_id: number | null;
}

type TipoEmpleado = 'administrador' | 'encargado_sucursal' | 'cajero';
type TopTab = 'usuarios' | 'permisos';

const TIPO_LABEL: Record<TipoEmpleado, string> = {
  administrador: 'Administradores',
  encargado_sucursal: 'Encargados de Sucursal',
  cajero: 'Cajeros',
};

const TIPO_A_ROL: Record<TipoEmpleado, string> = {
  administrador: 'Administrador',
  encargado_sucursal: 'Encargado de Sucursal',
  cajero: 'Cajero',
};

// Roles con matriz de permisos por empresa (el resto es de la plataforma).
const ROLES_TIENDA = new Set(['Administrador', 'Encargado de Sucursal', 'Cajero']);

// CU02 Administrar usuarios, roles y permisos. El administrador de una tienda
// ve solo su empresa. El SuperAdministrador elige primero la empresa (solo
// las activas con suscripción vigente) y recién ahí ve su personal o su
// matriz de permisos, con los CUs del 1er parcial arriba y los del 2do abajo.
@Component({
  selector: 'app-admin-usuarios',
  imports: [RouterLink],
  templateUrl: './usuarios.html',
  styleUrl: './usuarios.scss',
})
export class AdminUsuarios implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly plataforma = inject(PlataformaApi);

  protected readonly menu = ADMIN_MENU;
  protected readonly parciales = PARCIALES;
  protected readonly tipoLabel = TIPO_LABEL;
  protected readonly esSuper = this.auth.isSuperAdmin();

  protected readonly topTab = signal<TopTab>('usuarios');
  protected readonly tipoActivo = signal<TipoEmpleado>('administrador');

  protected readonly empleados = signal<Empleado[]>([]);
  protected readonly sucursales = signal<Sucursal[]>([]);
  protected readonly roles = signal<Rol[]>([]);
  protected readonly permisosDisponibles = signal<Permiso[]>([]);
  protected readonly buscar = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  // ---- SuperAdministrador: empresa elegida en cada pestaña
  protected readonly empresas = signal<EmpresaTenant[]>([]);
  protected readonly empresasCargando = signal(false);
  protected readonly empresaUsuarios = signal<EmpresaTenant | null>(null);
  protected readonly empresaPermisos = signal<EmpresaTenant | null>(null);
  // Personal del tipo activo en todas las empresas (para contar por empresa).
  private readonly personalTipo = signal<Empleado[]>([]);

  protected readonly conteoPorEmpresa = computed(() => {
    const mapa = new Map<number, number>();
    for (const e of this.personalTipo()) {
      if (e.empresa_id != null) mapa.set(e.empresa_id, (mapa.get(e.empresa_id) ?? 0) + 1);
    }
    return mapa;
  });

  protected readonly requiereSucursal = computed(() => this.tipoActivo() !== 'administrador');

  protected readonly rolesEmpleado = computed(() =>
    this.roles().filter((r) => r.nombre === TIPO_A_ROL[this.tipoActivo()]),
  );

  // Roles que se configuran desde esta pantalla.
  protected readonly rolesPermisos = computed(() =>
    this.roles().filter((r) => this.esSuper || ROLES_TIENDA.has(r.nombre)),
  );

  // Sucursales que se ofrecen al crear/editar: las de la empresa en curso.
  protected readonly sucursalesEmpresa = computed(() => {
    const empresa = this.empresaUsuarios();
    return empresa ? this.sucursales().filter((s) => s.empresa_id === empresa.id) : this.sucursales();
  });

  protected readonly permisoIdPorCodigo = computed(() => {
    const mapa = new Map<string, number>();
    for (const p of this.permisosDisponibles()) mapa.set(p.nombre, p.id);
    return mapa;
  });

  // formulario crear/editar empleado
  protected readonly showForm = signal(false);
  protected readonly editingId = signal<number | null>(null);
  protected readonly fNombre = signal('');
  protected readonly fEmail = signal('');
  protected readonly fSucursalId = signal<number | null>(null);
  protected readonly fRolId = signal<number | null>(null);
  protected readonly fEstado = signal('activo');
  protected readonly saving = signal(false);

  // matriz de permisos
  protected readonly rolSeleccionadoId = signal<number | null>(null);
  protected readonly permisosSeleccionados = signal<Set<number>>(new Set());
  protected readonly permisosSaving = signal(false);
  protected readonly permisosError = signal('');
  protected readonly permisosSuccess = signal('');

  protected readonly rolSeleccionado = computed(
    () => this.roles().find((r) => r.id === this.rolSeleccionadoId()) ?? null,
  );

  // El rol elegido tiene matriz por empresa (y por lo tanto pide empresa).
  protected readonly rolPorEmpresa = computed(() => {
    const rol = this.rolSeleccionado();
    return !!rol && ROLES_TIENDA.has(rol.nombre);
  });

  // ¿Ya se puede mostrar la matriz? Para el SuperAdministrador, con un rol de
  // tienda primero tiene que elegir la empresa.
  protected readonly mostrarMatriz = computed(
    () => !!this.rolSeleccionado() && (!this.esSuper || !this.rolPorEmpresa() || !!this.empresaPermisos()),
  );

  ngOnInit(): void {
    void this.loadCommon();
  }

  protected setTopTab(tab: TopTab): void {
    this.topTab.set(tab);
    if (tab === 'permisos' && this.rolSeleccionadoId() === null && this.rolesPermisos().length) {
      void this.selectRol(this.rolesPermisos()[0].id);
    }
  }

  protected setTipoActivo(tipo: TipoEmpleado): void {
    this.tipoActivo.set(tipo);
    this.buscar.set('');
    // SuperAdministrador: cada cargo arranca mostrando las empresas.
    if (this.esSuper) this.empresaUsuarios.set(null);
    void this.loadEmpleados();
  }

  protected search(): void {
    void this.loadEmpleados();
  }

  protected tableColspan(): number {
    return this.requiereSucursal() ? 7 : 6;
  }

  // ---------- SuperAdministrador: empresas ----------

  protected elegirEmpresaUsuarios(e: EmpresaTenant | null): void {
    this.empresaUsuarios.set(e);
    this.buscar.set('');
    void this.loadEmpleados();
  }

  protected async elegirEmpresaPermisos(e: EmpresaTenant | null): Promise<void> {
    this.empresaPermisos.set(e);
    this.permisosError.set('');
    this.permisosSuccess.set('');
    await this.loadRoles();
    const rol = this.rolSeleccionadoId();
    if (rol !== null) this.cargarSeleccion(rol);
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  // ---------- empleados CRUD ----------

  protected openCreate(): void {
    this.editingId.set(null);
    this.fNombre.set('');
    this.fEmail.set('');
    this.fSucursalId.set(this.sucursalesEmpresa()[0]?.id ?? null);
    this.fRolId.set(this.rolesEmpleado()[0]?.id ?? null);
    this.fEstado.set('activo');
    this.error.set('');
    this.showForm.set(true);
  }

  protected editEmpleado(e: Empleado): void {
    this.editingId.set(e.id);
    this.fNombre.set(e.nombre);
    this.fEmail.set(e.email);
    this.fSucursalId.set(e.sucursal_id);
    this.fRolId.set(e.rol_id);
    this.fEstado.set(e.estado);
    this.error.set('');
    this.showForm.set(true);
  }

  protected closeForm(): void {
    this.showForm.set(false);
  }

  protected async submitForm(): Promise<void> {
    if (!this.fNombre() || (!this.editingId() && !this.fEmail())) {
      this.error.set('Completa nombre y correo.');
      return;
    }
    if (this.requiereSucursal() && !this.fSucursalId()) {
      this.error.set('Selecciona una sucursal para este cargo.');
      return;
    }

    this.error.set('');
    this.saving.set(true);
    try {
      const id = this.editingId();
      if (id) {
        await firstValueFrom(
          this.http.put(`${environment.apiUrl}/empleados/${id}`, {
            nombre: this.fNombre(),
            sucursal_id: this.requiereSucursal() ? this.fSucursalId() : null,
            rol_id: this.fRolId(),
            estado: this.fEstado(),
          }),
        );
      } else {
        await firstValueFrom(
          this.http.post(`${environment.apiUrl}/empleados`, {
            nombre: this.fNombre(),
            email: this.fEmail(),
            tipo: this.tipoActivo(),
            sucursal_id: this.requiereSucursal() ? this.fSucursalId() : null,
            rol_id: this.fRolId(),
            empresa_id: this.empresaUsuarios()?.id ?? null,
          }),
        );
      }
      this.showForm.set(false);
      await this.loadEmpleados();
    } catch (err) {
      this.error.set(this.extractError(err));
    } finally {
      this.saving.set(false);
    }
  }

  protected async toggleEstado(e: Empleado): Promise<void> {
    const nuevoEstado = e.estado === 'activo' ? 'inactivo' : 'activo';
    const accion = nuevoEstado === 'inactivo' ? 'desactivar' : 'activar';
    if (!confirm(`¿Seguro que quieres ${accion} a "${e.nombre}"?`)) return;

    try {
      await firstValueFrom(
        this.http.put(`${environment.apiUrl}/empleados/${e.id}`, {
          nombre: e.nombre,
          sucursal_id: e.sucursal_id,
          rol_id: e.rol_id,
          estado: nuevoEstado,
        }),
      );
      await this.loadEmpleados();
    } catch (err) {
      this.error.set(this.extractError(err));
    }
  }

  // ---------- permisos ----------

  protected async selectRol(rolId: number): Promise<void> {
    this.rolSeleccionadoId.set(rolId);
    this.permisosError.set('');
    this.permisosSuccess.set('');
    // SuperAdministrador: al elegir un rol se vuelve a la lista de empresas.
    if (this.esSuper && this.empresaPermisos()) {
      this.empresaPermisos.set(null);
      await this.loadRoles();
    }
    this.cargarSeleccion(rolId);
  }

  private cargarSeleccion(rolId: number): void {
    const rol = this.roles().find((r) => r.id === rolId);
    const codigos = new Set(rol?.permisos ?? []);
    const ids = new Set(
      this.permisosDisponibles()
        .filter((p) => codigos.has(p.nombre))
        .map((p) => p.id),
    );
    this.permisosSeleccionados.set(ids);
  }

  protected permisoIdForCode(code: string): number {
    return this.permisoIdPorCodigo().get(code) ?? -1;
  }

  protected togglePermiso(permisoId: number): void {
    if (permisoId === -1 || this.rolSeleccionado()?.nombre === 'Administrador') return;
    const actuales = new Set(this.permisosSeleccionados());
    if (actuales.has(permisoId)) actuales.delete(permisoId);
    else actuales.add(permisoId);
    this.permisosSeleccionados.set(actuales);
  }

  // Un CU del 2do parcial puede agrupar varios permisos (CU04 = productos,
  // catálogo e inventario): está marcado si los tiene todos.
  protected casoMarcado(caso: CasoUsoMenu): boolean {
    const ids = permisosDe(caso).map((c) => this.permisoIdForCode(c));
    return ids.every((id) => id !== -1 && this.permisosSeleccionados().has(id));
  }

  // Tiene algunos de los permisos del CU pero no todos (casilla intermedia).
  protected casoParcial(caso: CasoUsoMenu): boolean {
    const ids = permisosDe(caso).map((c) => this.permisoIdForCode(c));
    const tiene = ids.filter((id) => this.permisosSeleccionados().has(id)).length;
    return tiene > 0 && tiene < ids.length;
  }

  protected toggleCaso(caso: CasoUsoMenu): void {
    if (this.rolSeleccionado()?.nombre === 'Administrador') return;
    const ids = permisosDe(caso)
      .map((c) => this.permisoIdForCode(c))
      .filter((id) => id !== -1);
    const marcar = !this.casoMarcado(caso);
    const actuales = new Set(this.permisosSeleccionados());
    for (const id of ids) {
      if (marcar) actuales.add(id);
      else actuales.delete(id);
    }
    this.permisosSeleccionados.set(actuales);
  }

  protected async guardarPermisos(): Promise<void> {
    const rol = this.rolSeleccionado();
    if (!rol) return;

    this.permisosError.set('');
    this.permisosSuccess.set('');
    this.permisosSaving.set(true);
    try {
      const empresa = this.rolPorEmpresa() ? this.empresaPermisos() : null;
      const rolActualizado = await firstValueFrom(
        this.http.put<Rol>(
          `${environment.apiUrl}/roles/${rol.id}/permisos`,
          { permiso_ids: Array.from(this.permisosSeleccionados()) },
          empresa ? { params: { empresa_id: empresa.id } } : {},
        ),
      );
      this.roles.update((lista) => lista.map((r) => (r.id === rolActualizado.id ? rolActualizado : r)));
      this.permisosSuccess.set(empresa ? `Permisos actualizados para ${empresa.nombre}.` : 'Permisos actualizados.');
    } catch (err) {
      this.permisosError.set(this.extractError(err));
    } finally {
      this.permisosSaving.set(false);
    }
  }

  // ---------- carga ----------

  private async loadCommon(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const permisos = await firstValueFrom(this.http.get<Permiso[]>(`${environment.apiUrl}/roles/permisos`));
      this.permisosDisponibles.set(permisos);
      await this.loadRoles();
    } catch {
      this.error.set('No se pudo cargar la información de roles y permisos.');
    }

    try {
      const sucursales = await firstValueFrom(this.http.get<Sucursal[]>(`${environment.apiUrl}/sucursales`));
      this.sucursales.set(sucursales);
    } catch {
      // si el usuario no tiene CU04, el desplegable de sucursal queda vacío
    }

    if (this.esSuper) await this.loadEmpresas();
    await this.loadEmpleados();
    this.loading.set(false);
  }

  // Roles con los permisos de la empresa elegida (o los globales).
  private async loadRoles(): Promise<void> {
    const empresa = this.esSuper ? this.empresaPermisos() : null;
    const roles = await firstValueFrom(
      this.http.get<Rol[]>(`${environment.apiUrl}/roles`, empresa ? { params: { empresa_id: empresa.id } } : {}),
    );
    this.roles.set(roles);
  }

  // Empresas registradas, activas y con suscripción vigente.
  private async loadEmpresas(): Promise<void> {
    this.empresasCargando.set(true);
    try {
      const todas = await this.plataforma.empresas();
      this.empresas.set(todas.filter((e) => e.estado === 'activa' && e.planCodigo));
    } catch {
      this.error.set('No se pudieron cargar las empresas.');
    } finally {
      this.empresasCargando.set(false);
    }
  }

  private async loadEmpleados(): Promise<void> {
    // SuperAdministrador sin empresa elegida: se trae el personal de todas
    // solo para contar cuántos tiene cada empresa en los cuadros.
    const empresa = this.esSuper ? this.empresaUsuarios() : null;
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = { tipo: this.tipoActivo() };
      if (this.buscar().trim()) params['buscar'] = this.buscar().trim();
      if (empresa) params['empresa_id'] = String(empresa.id);
      const res = await firstValueFrom(this.http.get<Empleado[]>(`${environment.apiUrl}/empleados`, { params }));
      if (this.esSuper && !empresa) {
        this.personalTipo.set(res);
        this.empleados.set([]);
      } else {
        this.empleados.set(res);
      }
    } catch {
      this.error.set('No se pudo cargar los empleados.');
    } finally {
      this.loading.set(false);
    }
  }

  private extractError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'Ocurrió un error inesperado.';
  }
}
