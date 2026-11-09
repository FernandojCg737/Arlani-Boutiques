import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import { EmpresaTenant, PlataformaApi, mensajeError } from '../../../services/plataforma';

interface Seccion {
  codigo: string;
  nombre: string;
}

interface Estado {
  disponible: boolean;
  sistema: boolean;
  plan: string | null;
  secciones: Seccion[];
}

interface Backup {
  id: number;
  alcance: string;
  secciones: string[];
  origen: 'manual' | 'programado' | 'antes_de_restaurar' | 'importado';
  programacion_nombre: string | null;
  estado: 'en_proceso' | 'completado' | 'fallido';
  tamano_bytes: number | null;
  conteos: Record<string, number> | null;
  imagenes: number | null;
  atrasado: boolean;
  error: string | null;
  creado_por: string | null;
  creado_en: string;
}

interface ResumenTabla {
  volvieron: number;
  actualizadas: number;
  omitidas: number;
  motivo?: string;
}

interface Restauracion {
  id: number;
  backup_id: number | null;
  backup_creado_en: string | null;
  secciones: string[];
  estado: 'en_proceso' | 'completada' | 'fallida';
  resumen: { tablas: Record<string, ResumenTabla>; imagenes: number } | null;
  backup_previo_id: number | null;
  error: string | null;
  hecho_por: string | null;
  creado_en: string;
}

interface Programacion {
  id: number;
  nombre: string;
  frecuencia: 'una_vez' | 'diaria' | 'semanal' | 'mensual';
  hora: string;
  fecha: string | null;
  dia_semana: number | null;
  dia_mes: number | null;
  secciones: string[];
  retener: number;
  activa: boolean;
  proxima_ejecucion: string | null;
  ultima_ejecucion: string | null;
  backups: number;
}

interface FormProgramacion {
  id: number | null;
  nombre: string;
  frecuencia: Programacion['frecuencia'];
  hora: string;
  fecha: string;
  dia_semana: number;
  dia_mes: number;
  secciones: string[];
  retener: number;
  activa: boolean;
}

type Pestana = 'backups' | 'programacion' | 'restauraciones';

export const DIAS_SEMANA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

// Lo que se muestra del contenido de un backup (tabla -> etiqueta).
const CONTEO_ETIQUETA: Record<string, string> = {
  producto: 'productos',
  inventario: 'registros de stock',
  sucursal: 'sucursales',
  usuario_personal: 'empleados',
  venta: 'ventas',
  reserva: 'reservas',
  pago: 'pagos',
  caja: 'cajas',
  empresa: 'tiendas',
  usuario_cliente: 'clientes',
};

// CU21 Gestionar backups y restauración. El Administrador de una tienda (o su
// personal con el permiso 2P-CU21) respalda y restaura lo suyo; el
// SuperAdministrador elige "Sistema completo" o una tienda. Restaurar es un
// merge: nunca borra lo que hay hoy.
@Component({
  selector: 'app-admin-backups',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './backups.html',
  styleUrls: ['../ventas/ventas.scss', './backups.scss'],
})
export class AdminBackups implements OnInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly plataforma = inject(PlataformaApi);
  private readonly api = `${environment.apiUrl}/backups`;
  private sondeo: ReturnType<typeof setInterval> | null = null;

  protected readonly esSuper = this.auth.isSuperAdmin();
  protected readonly diasSemana = DIAS_SEMANA;
  protected readonly tiendas = signal<EmpresaTenant[]>([]);
  // SuperAdministrador: null = sistema completo.
  protected readonly empresaId = signal<number | null>(null);

  protected readonly pestana = signal<Pestana>('backups');
  protected readonly estado = signal<Estado | null>(null);
  protected readonly backups = signal<Backup[]>([]);
  protected readonly restauraciones = signal<Restauracion[]>([]);
  protected readonly programaciones = signal<Programacion[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly aviso = signal('');

  protected readonly seleccion = signal<string[]>([]);
  protected readonly creando = signal(false);
  protected readonly importando = signal(false);

  protected readonly restaurando = signal<Backup | null>(null);
  protected readonly seccionesRestaurar = signal<string[]>([]);
  protected readonly confirmacion = signal('');
  protected readonly errorModal = signal('');
  protected readonly guardando = signal(false);

  protected readonly form = signal<FormProgramacion | null>(null);

  protected readonly nombreSeccion = computed(() => {
    const mapa: Record<string, string> = {};
    for (const s of this.estado()?.secciones ?? []) mapa[s.codigo] = s.nombre;
    return mapa;
  });
  protected readonly enProceso = computed(
    () => this.backups().some((b) => b.estado === 'en_proceso') || this.restauraciones().some((r) => r.estado === 'en_proceso'),
  );

  async ngOnInit(): Promise<void> {
    if (this.esSuper) {
      this.plataforma.empresas().then((t) => this.tiendas.set(t), () => undefined);
    }
    await this.cargar();
    // Mientras un backup o una restauración se están haciendo, se refresca solo.
    this.sondeo = setInterval(() => {
      if (this.enProceso()) void this.cargar(false);
    }, 4000);
  }

  ngOnDestroy(): void {
    if (this.sondeo) clearInterval(this.sondeo);
  }

  private params(): Record<string, string> {
    const id = this.empresaId();
    return this.esSuper && id !== null ? { empresa_id: String(id) } : {};
  }

  protected async cargar(conIndicador = true): Promise<void> {
    if (conIndicador) this.cargando.set(true);
    this.error.set('');
    try {
      const params = this.params();
      const [estado, backups, restauraciones, programaciones] = await Promise.all([
        firstValueFrom(this.http.get<Estado>(`${this.api}/estado`, { params })),
        firstValueFrom(this.http.get<Backup[]>(this.api, { params })),
        firstValueFrom(this.http.get<Restauracion[]>(`${this.api}/restauraciones`, { params })),
        firstValueFrom(this.http.get<Programacion[]>(`${this.api}/programaciones`, { params })),
      ]);
      if (!this.estado() || this.estado()!.sistema !== estado.sistema) this.seleccion.set(estado.secciones.map((s) => s.codigo));
      this.estado.set(estado);
      this.backups.set(backups);
      this.restauraciones.set(restauraciones);
      this.programaciones.set(programaciones);
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar los backups.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected elegirAmbito(valor: string): void {
    this.empresaId.set(valor ? Number(valor) : null);
    this.estado.set(null);
    this.aviso.set('');
    void this.cargar();
  }

  // Las fechas del backend vienen en UTC sin zona.
  protected utc(fecha: string | null): string | null {
    if (!fecha) return null;
    return /[zZ]|[+-]\d\d:?\d\d$/.test(fecha) ? fecha : fecha + 'Z';
  }

  protected alternar(lista: string[], codigo: string): string[] {
    return lista.includes(codigo) ? lista.filter((c) => c !== codigo) : [...lista, codigo];
  }

  protected tamano(bytes: number | null): string {
    if (bytes === null) return '—';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  protected contenido(b: Backup): string {
    const partes = Object.entries(CONTEO_ETIQUETA)
      .filter(([clave]) => (b.conteos?.[clave] ?? 0) > 0)
      .map(([clave, etiqueta]) => `${b.conteos![clave]} ${etiqueta}`);
    if (b.imagenes) partes.push(`${b.imagenes} imágenes`);
    return partes.join(' · ');
  }

  protected origen(b: Backup): string {
    if (b.origen === 'manual') return 'Manual';
    if (b.origen === 'antes_de_restaurar') return 'Automático antes de restaurar';
    if (b.origen === 'importado') return 'Importado desde un archivo';
    return `Programado${b.programacion_nombre ? ': ' + b.programacion_nombre : ''}`;
  }

  // ------------------------------------------------------------ backups

  protected async crear(): Promise<void> {
    if (!this.seleccion().length) {
      this.error.set('Elige al menos una sección.');
      return;
    }
    this.creando.set(true);
    this.error.set('');
    this.aviso.set('');
    try {
      await firstValueFrom(this.http.post(this.api, { secciones: this.seleccion() }, { params: this.params() }));
      this.aviso.set('Haciendo el backup: en unos segundos aparece como completado.');
      await this.cargar(false);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo iniciar el backup.'));
    } finally {
      this.creando.set(false);
    }
  }

  protected async descargar(b: Backup): Promise<void> {
    try {
      const blob = await firstValueFrom(
        this.http.get(`${this.api}/${b.id}/descargar`, { params: this.params(), responseType: 'blob' }),
      );
      const enlace = document.createElement('a');
      enlace.href = URL.createObjectURL(blob);
      enlace.download = `arlani-backup-${b.id}.zip`;
      enlace.click();
      URL.revokeObjectURL(enlace.href);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo descargar el backup.'));
    }
  }

  // Sube un ZIP descargado antes: queda como un backup más y se abre
  // directamente el diálogo para restaurarlo.
  protected async importar(input: HTMLInputElement): Promise<void> {
    const archivo = input.files?.[0];
    input.value = '';
    if (!archivo) return;
    if (!archivo.name.toLowerCase().endsWith('.zip')) {
      this.error.set('Elige el archivo .zip de un backup descargado de Arlani.');
      return;
    }
    this.importando.set(true);
    this.error.set('');
    this.aviso.set('');
    try {
      const datos = new FormData();
      datos.append('archivo', archivo);
      const b = await firstValueFrom(this.http.post<Backup>(`${this.api}/importar`, datos, { params: this.params() }));
      await this.cargar(false);
      this.aviso.set(`Backup importado como #${b.id}: elige qué restaurar.`);
      this.abrirRestaurar(b);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo importar el backup.'));
    } finally {
      this.importando.set(false);
    }
  }

  protected async borrar(b: Backup): Promise<void> {
    if (!confirm(`¿Borrar el backup #${b.id}? Su archivo se elimina y no se podrá restaurar.`)) return;
    try {
      await firstValueFrom(this.http.delete(`${this.api}/${b.id}`, { params: this.params() }));
      await this.cargar(false);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo borrar el backup.'));
    }
  }

  // ------------------------------------------------------------ restaurar

  protected abrirRestaurar(b: Backup): void {
    // El historial va desmarcado: se pregunta aparte (es un merge).
    this.seccionesRestaurar.set(b.secciones.filter((s) => s !== 'historial'));
    this.confirmacion.set('');
    this.errorModal.set('');
    this.restaurando.set(b);
  }

  protected cerrarRestaurar(): void {
    if (!this.guardando()) this.restaurando.set(null);
  }

  protected async confirmarRestaurar(): Promise<void> {
    const b = this.restaurando();
    if (!b) return;
    if (!this.seccionesRestaurar().length) {
      this.errorModal.set('Elige al menos una sección.');
      return;
    }
    if (this.estado()?.sistema && this.confirmacion().trim().toUpperCase() !== 'RESTAURAR') {
      this.errorModal.set('Para restaurar el sistema completo escribe RESTAURAR.');
      return;
    }
    this.guardando.set(true);
    this.errorModal.set('');
    try {
      await firstValueFrom(
        this.http.post(
          `${this.api}/${b.id}/restaurar`,
          { secciones: this.seccionesRestaurar(), confirmacion: this.confirmacion() || null },
          { params: this.params() },
        ),
      );
      this.restaurando.set(null);
      this.pestana.set('restauraciones');
      this.aviso.set('Restaurando: primero se hace un backup de cómo está todo ahora y luego se restaura.');
      await this.cargar(false);
    } catch (err) {
      this.errorModal.set(mensajeError(err, 'No se pudo restaurar.'));
    } finally {
      this.guardando.set(false);
    }
  }

  protected totales(r: Restauracion): { volvieron: number; actualizadas: number; omitidas: number } {
    const t = { volvieron: 0, actualizadas: 0, omitidas: 0 };
    for (const x of Object.values(r.resumen?.tablas ?? {})) {
      t.volvieron += x.volvieron;
      t.actualizadas += x.actualizadas;
      t.omitidas += x.omitidas;
    }
    return t;
  }

  protected omitidas(r: Restauracion): string[] {
    return Object.entries(r.resumen?.tablas ?? {})
      .filter(([, x]) => x.omitidas > 0)
      .map(([tabla, x]) => `${tabla}: ${x.omitidas}${x.motivo ? ' (' + x.motivo + ')' : ''}`);
  }

  // ---------------------------------------------------------- programación

  protected nuevaProgramacion(): void {
    this.errorModal.set('');
    this.form.set({
      id: null,
      nombre: 'Backup diario',
      frecuencia: 'diaria',
      hora: '03:00',
      fecha: '',
      dia_semana: 0,
      dia_mes: 1,
      secciones: (this.estado()?.secciones ?? []).map((s) => s.codigo),
      retener: 10,
      activa: true,
    });
  }

  protected editarProgramacion(p: Programacion): void {
    this.errorModal.set('');
    this.form.set({
      id: p.id,
      nombre: p.nombre,
      frecuencia: p.frecuencia,
      hora: p.hora.slice(0, 5),
      fecha: p.fecha ?? '',
      dia_semana: p.dia_semana ?? 0,
      dia_mes: p.dia_mes ?? 1,
      secciones: p.secciones,
      retener: p.retener,
      activa: p.activa,
    });
  }

  protected cambiarForm(cambios: Partial<FormProgramacion>): void {
    this.form.update((f) => (f ? { ...f, ...cambios } : f));
  }

  protected async guardarProgramacion(): Promise<void> {
    const f = this.form();
    if (!f) return;
    if (!f.nombre.trim() || !f.secciones.length) {
      this.errorModal.set('Ponle un nombre y elige al menos una sección.');
      return;
    }
    if (f.frecuencia === 'una_vez' && !f.fecha) {
      this.errorModal.set('Elige la fecha.');
      return;
    }
    const cuerpo = {
      nombre: f.nombre.trim(),
      frecuencia: f.frecuencia,
      hora: f.hora,
      fecha: f.frecuencia === 'una_vez' ? f.fecha : null,
      dia_semana: f.frecuencia === 'semanal' ? f.dia_semana : null,
      dia_mes: f.frecuencia === 'mensual' ? f.dia_mes : null,
      secciones: f.secciones,
      retener: f.retener,
      activa: f.activa,
    };
    this.guardando.set(true);
    this.errorModal.set('');
    try {
      const params = this.params();
      await firstValueFrom(
        f.id === null
          ? this.http.post(`${this.api}/programaciones`, cuerpo, { params })
          : this.http.put(`${this.api}/programaciones/${f.id}`, cuerpo, { params }),
      );
      this.form.set(null);
      await this.cargar(false);
    } catch (err) {
      this.errorModal.set(mensajeError(err, 'No se pudo guardar la programación.'));
    } finally {
      this.guardando.set(false);
    }
  }

  protected async pausar(p: Programacion): Promise<void> {
    this.editarProgramacion(p);
    this.cambiarForm({ activa: !p.activa });
    await this.guardarProgramacion();
    if (this.errorModal()) this.error.set(this.errorModal());
  }

  protected async borrarProgramacion(p: Programacion): Promise<void> {
    if (!confirm(`¿Borrar la programación "${p.nombre}"? Los backups que ya hizo se conservan.`)) return;
    try {
      await firstValueFrom(this.http.delete(`${this.api}/programaciones/${p.id}`, { params: this.params() }));
      await this.cargar(false);
    } catch (err) {
      this.error.set(mensajeError(err, 'No se pudo borrar la programación.'));
    }
  }

  protected cuando(p: Programacion): string {
    const hora = p.hora.slice(0, 5);
    switch (p.frecuencia) {
      case 'una_vez':
        return `Una vez, el ${p.fecha?.split('-').reverse().join('/')} a las ${hora}`;
      case 'diaria':
        return `Todos los días a las ${hora}`;
      case 'semanal':
        return `Cada ${DIAS_SEMANA[p.dia_semana ?? 0]} a las ${hora}`;
      default:
        return `El día ${p.dia_mes} de cada mes a las ${hora}${(p.dia_mes ?? 0) > 28 ? ' (o el último día del mes)' : ''}`;
    }
  }
}
