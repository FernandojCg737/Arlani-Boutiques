import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import { EmpresaTenant, PlataformaApi } from '../../../services/plataforma';

interface UsuarioActivo {
  id: number;
  nombre: string;
  email: string;
  tipo: string;
  rol: string | null;
  empresa_id: number | null;
  empresa_nombre: string | null;
  sucursal_nombre: string | null;
  expira_en: string;
}

// Filtro de sesiones del SuperAdministrador: todo, solo cuentas de la
// plataforma (clientes y él mismo) o una empresa puntual.
type FiltroSesiones = 'todas' | 'plataforma' | number;

const TIPO_TEXTO: Record<string, string> = {
  superadministrador: 'SuperAdministrador',
  administrador: 'Administrador',
  encargado_sucursal: 'Encargado de sucursal',
  cajero: 'Cajero',
  cliente: 'Cliente',
  proveedor: 'Proveedor',
};

interface EstadoAsistencia {
  liberado: boolean;
  ventana_cerrada: boolean;
  hora_liberacion: string;
  codigo_fecha: string;
  codigo: string | null;
}

interface MarcadoHoy {
  empleado_id: number;
  empleado_nombre: string;
  sucursal_nombre: string | null;
  marco: boolean;
  hora_marcado: string | null;
  estado: 'marco' | 'pendiente' | 'falta';
}

interface Marcado {
  id: number;
  empleado_id: number;
  empleado_nombre: string;
  sucursal_nombre: string | null;
  fecha: string;
  hora_marcado: string;
  latitud: number;
  longitud: number;
  foto_url: string | null;
}

const DIAS_SEMANA = ['Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo'];
const TZ_BOLIVIA = 'America/La_Paz';

@Component({
  selector: 'app-admin-sesiones',
  imports: [DatePipe, NgTemplateOutlet],
  templateUrl: './sesiones.html',
  styleUrl: './sesiones.scss',
})
// CU01 Inicio y cierre de sesión + control de asistencia.
// - SuperAdministrador: ve las sesiones de todo el sistema (filtrables por
//   empresa) y el control de asistencia de la empresa que elija, solo lectura.
// - Administrador de una tienda: ve las sesiones de sus Encargados y Cajeros
//   y gestiona el control de asistencia de su empresa.
// - Encargado / Cajero: marca su asistencia.
export class AdminSesiones implements OnInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly plataforma = inject(PlataformaApi);
  protected readonly auth = inject(Auth);
  protected readonly tzBolivia = TZ_BOLIVIA;
  protected readonly tipoTexto = TIPO_TEXTO;

  protected readonly esSuper = this.auth.isSuperAdmin();
  protected readonly esAdminTienda = this.auth.currentUser()?.tipo === 'administrador';

  // ---- SuperAdministrador: empresa elegida
  protected readonly empresas = signal<EmpresaTenant[]>([]);
  protected readonly filtro = signal<FiltroSesiones>('todas');
  protected readonly empresaElegida = computed(() => {
    const f = this.filtro();
    return typeof f === 'number' ? (this.empresas().find((e) => e.id === f) ?? null) : null;
  });

  protected readonly items = signal<UsuarioActivo[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  // ---- Asistencia: comun a todos ----
  protected readonly estado = signal<EstadoAsistencia | null>(null);
  protected readonly cargandoEstado = signal(false);
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  // ---- Asistencia: solo Administrador ----
  protected readonly nuevaHora = signal('08:00');
  protected readonly guardandoHora = signal(false);
  protected readonly liberando = signal(false);
  protected readonly marcadosHoy = signal<MarcadoHoy[]>([]);
  protected readonly historial = signal<Marcado[]>([]);
  protected readonly cargandoAdmin = signal(false);
  protected readonly mensajeAdmin = signal('');

  // ---- Asistencia: solo staff (Encargado/Cajero) ----
  protected readonly codigoIngresado = signal('');
  protected readonly fotoSeleccionada = signal<File | null>(null);
  protected readonly fotoPreviewUrl = signal<string | null>(null);
  protected readonly marcando = signal(false);
  protected readonly mensajeMarcado = signal('');
  protected readonly errorMarcado = signal('');
  protected readonly miHistorial = signal<Marcado[]>([]);

  protected readonly diasSemana = DIAS_SEMANA;

  ngOnInit(): void {
    this.load();
    if (this.esSuper) {
      void this.cargarEmpresas();
    } else {
      this.cargarEstado();
      if (this.esAdminTienda) {
        this.cargarHoy();
        this.cargarHistorial();
      } else {
        this.cargarMiHistorial();
      }
    }
    // Refresca el estado (cuenta regresiva de la ventana de 5 min) cada 10s,
    // sin depender del heartbeat general de sesion.
    this.pollTimer = setInterval(() => this.cargarEstado(), 10_000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    const preview = this.fotoPreviewUrl();
    if (preview) URL.revokeObjectURL(preview);
  }

  protected refrescar(): void {
    this.load();
    this.cargarEstado();
    if (this.esSuper && this.empresaElegida()) {
      this.cargarHoy();
      this.cargarHistorial();
    }
  }

  // SuperAdministrador: cambiar de empresa filtra las sesiones y, si es una
  // empresa, muestra su control de asistencia (solo lectura).
  protected elegirFiltro(f: FiltroSesiones): void {
    this.filtro.set(f);
    this.estado.set(null);
    this.marcadosHoy.set([]);
    this.historial.set([]);
    this.load();
    if (typeof f === 'number') {
      this.cargarEstado();
      this.cargarHoy();
      this.cargarHistorial();
    }
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  private async cargarEmpresas(): Promise<void> {
    try {
      this.empresas.set(await this.plataforma.empresas());
    } catch {
      this.error.set('No se pudieron cargar las empresas.');
    }
  }

  // Parámetros según el perfil: el SuperAdministrador manda la empresa.
  private paramsEmpresa(): Record<string, string> {
    const empresa = this.empresaElegida();
    return this.esSuper && empresa ? { empresa_id: String(empresa.id) } : {};
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const f = this.filtro();
      const params: Record<string, string> = !this.esSuper
        ? {}
        : typeof f === 'number'
          ? { empresa_id: String(f) }
          : f === 'plataforma'
            ? { plataforma: 'true' }
            : {};
      const res = await firstValueFrom(
        this.http.get<UsuarioActivo[]>(`${environment.apiUrl}/sesiones/activas`, { params }),
      );
      this.items.set(res);
    } catch {
      this.error.set('No se pudo cargar las sesiones activas.');
    } finally {
      this.loading.set(false);
    }
  }

  protected async cargarEstado(): Promise<void> {
    // El SuperAdministrador solo ve el estado de una empresa elegida.
    if (this.esSuper && !this.empresaElegida()) return;
    this.cargandoEstado.set(true);
    try {
      const res = await firstValueFrom(
        this.http.get<EstadoAsistencia>(`${environment.apiUrl}/asistencia/estado`, { params: this.paramsEmpresa() }),
      );
      this.estado.set(res);
      this.nuevaHora.set(res.hora_liberacion.slice(0, 5));
    } catch {
      // silencioso: no bloquea el resto de la pantalla
    } finally {
      this.cargandoEstado.set(false);
    }
  }

  protected async guardarHora(): Promise<void> {
    this.guardandoHora.set(true);
    this.mensajeAdmin.set('');
    try {
      const res = await firstValueFrom(
        this.http.put<EstadoAsistencia>(`${environment.apiUrl}/asistencia/hora`, {
          hora_liberacion: `${this.nuevaHora()}:00`,
        }),
      );
      this.estado.set(res);
      this.mensajeAdmin.set('Hora de liberacion actualizada.');
    } catch {
      this.mensajeAdmin.set('No se pudo actualizar la hora.');
    } finally {
      this.guardandoHora.set(false);
    }
  }

  protected async liberarAhora(): Promise<void> {
    this.liberando.set(true);
    this.mensajeAdmin.set('');
    try {
      const res = await firstValueFrom(this.http.post<EstadoAsistencia>(`${environment.apiUrl}/asistencia/liberar`, {}));
      this.estado.set(res);
      this.mensajeAdmin.set('Clave liberada por 5 minutos.');
      this.cargarHoy();
    } catch {
      this.mensajeAdmin.set('No se pudo liberar la clave.');
    } finally {
      this.liberando.set(false);
    }
  }

  private async cargarHoy(): Promise<void> {
    this.cargandoAdmin.set(true);
    try {
      const res = await firstValueFrom(
        this.http.get<MarcadoHoy[]>(`${environment.apiUrl}/asistencia/hoy`, { params: this.paramsEmpresa() }),
      );
      this.marcadosHoy.set(res);
    } catch {
      // silencioso
    } finally {
      this.cargandoAdmin.set(false);
    }
  }

  private async cargarHistorial(): Promise<void> {
    try {
      const res = await firstValueFrom(
        this.http.get<Marcado[]>(`${environment.apiUrl}/asistencia/historial`, { params: this.paramsEmpresa() }),
      );
      this.historial.set(res);
    } catch {
      // silencioso
    }
  }

  private async cargarMiHistorial(): Promise<void> {
    try {
      const res = await firstValueFrom(this.http.get<Marcado[]>(`${environment.apiUrl}/asistencia/mia`));
      this.miHistorial.set(res);
    } catch {
      // silencioso
    }
  }

  // Mapea el historial propio a las 7 casillas Lunes-Domingo de la semana
  // actual, calculada en hora Bolivia (no la del navegador del visitante).
  protected filaSemanaActual(): { dia: string; marcado: Marcado | null }[] {
    const hoyBoliviaStr = new Date().toLocaleDateString('en-CA', { timeZone: TZ_BOLIVIA }); // YYYY-MM-DD
    const hoy = new Date(`${hoyBoliviaStr}T12:00:00`);
    const diaSemanaIso = (hoy.getDay() + 6) % 7; // 0=lunes ... 6=domingo
    const lunes = new Date(hoy);
    lunes.setDate(hoy.getDate() - diaSemanaIso);

    const porFecha = new Map(this.miHistorial().map((m) => [m.fecha, m]));

    return DIAS_SEMANA.map((dia, i) => {
      const fecha = new Date(lunes);
      fecha.setDate(lunes.getDate() + i);
      const iso = fecha.toISOString().slice(0, 10);
      return { dia, marcado: porFecha.get(iso) ?? null };
    });
  }

  protected onFotoSeleccionada(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    const anterior = this.fotoPreviewUrl();
    if (anterior) URL.revokeObjectURL(anterior);
    this.fotoSeleccionada.set(file);
    this.fotoPreviewUrl.set(file ? URL.createObjectURL(file) : null);
  }

  protected async marcarAsistencia(): Promise<void> {
    this.marcando.set(true);
    this.mensajeMarcado.set('');
    this.errorMarcado.set('');

    if (!this.fotoSeleccionada()) {
      this.errorMarcado.set('Toma una foto de verificacion antes de marcar.');
      this.marcando.set(false);
      return;
    }
    if (!navigator.geolocation) {
      this.errorMarcado.set('Tu navegador no permite obtener la ubicacion.');
      this.marcando.set(false);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const form = new FormData();
          form.append('codigo', this.codigoIngresado());
          form.append('latitud', String(pos.coords.latitude));
          form.append('longitud', String(pos.coords.longitude));
          form.append('foto', this.fotoSeleccionada()!);

          await firstValueFrom(this.http.post(`${environment.apiUrl}/asistencia/marcar`, form));
          this.mensajeMarcado.set('Asistencia marcada correctamente.');
          this.codigoIngresado.set('');
          const preview = this.fotoPreviewUrl();
          if (preview) URL.revokeObjectURL(preview);
          this.fotoSeleccionada.set(null);
          this.fotoPreviewUrl.set(null);
          this.cargarMiHistorial();
        } catch (e) {
          const err = e as HttpErrorResponse;
          this.errorMarcado.set(err.error?.detail ?? 'No se pudo marcar la asistencia.');
        } finally {
          this.marcando.set(false);
        }
      },
      () => {
        this.errorMarcado.set('No se pudo obtener tu ubicacion. Da permiso de ubicacion e intenta de nuevo.');
        this.marcando.set(false);
      },
    );
  }
}
