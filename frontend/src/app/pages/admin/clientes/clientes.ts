import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { MapaUbicacion } from '../../../components/mapa-ubicacion/mapa-ubicacion';
import { Auth } from '../../../services/auth';
import { enlaceMapa } from '../../../services/mapa';

interface Cliente {
  id: number;
  nombre: string;
  email: string;
  telefono: string | null;
  direccion: string | null;
  estado: string;
  fecha_registro: string;
  metodo_registro: string;
  // Solo viene al listar los clientes de una empresa.
  relacion: RelacionTienda | null;
  // Ubicacion de su ultima compra con envio a domicilio (para el
  // SuperAdministrador, en cualquier tienda; para una tienda, en la suya).
  ultima_ubicacion: UltimaUbicacion | null;
}

interface UltimaUbicacion {
  venta_id: number;
  fecha: string;
  tienda_nombre: string;
  direccion: string;
  referencia: string | null;
  ciudad: string | null;
  latitud: string;
  longitud: string;
}

interface RelacionTienda {
  compras: number;
  reservas: number;
  en_carrito: number;
  usos_probador: number;
  ultima_interaccion: string | null;
}

@Component({
  selector: 'app-admin-clientes',
  imports: [DatePipe, MapaUbicacion],
  templateUrl: './clientes.html',
  styleUrl: './clientes.scss',
})
// CU03. Los clientes son de la plataforma: el SuperAdministrador ve a todos
// (o los de una empresa con ?empresa=); cada tienda ve solo a los que
// trabajaron con ella (compraron, reservaron, tienen sus prendas en el
// carrito, usaron el probador o los registro su personal).
export class AdminClientes implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  protected readonly esSuper = inject(Auth).isSuperAdmin();

  // Dentro de la pantalla de empresas del SuperAdministrador (sin encabezado propio).
  readonly embebido = input(false);

  // Cliente cuya ultima ubicacion de envio se ve en el mapa.
  protected readonly ubicacionVista = signal<Cliente | null>(null);
  protected readonly enlaceMapa = enlaceMapa;

  // Empresa elegida por el SuperAdministrador (null = todos los clientes).
  protected readonly empresaId = computed(() => {
    if (!this.esSuper || this.embebido()) return null;
    const id = Number(this.route.snapshot.queryParamMap.get('empresa'));
    return id > 0 ? id : null;
  });
  // Con la relacion con la tienda: el personal de una tienda o el SuperAdministrador filtrando una.
  protected readonly conRelacion = computed(() => !this.esSuper || this.empresaId() !== null);
  // Un cliente creado por el SuperAdministrador no queda ligado a ninguna tienda,
  // asi que el alta se ofrece en la lista general.
  protected readonly puedeCrear = computed(() => !this.esSuper || this.empresaId() === null);
  protected readonly columnas = computed(() => (this.conRelacion() ? 8 : 7));

  protected readonly clientes = signal<Cliente[]>([]);
  protected readonly buscar = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  protected readonly showCreateForm = signal(false);
  protected readonly cNombre = signal('');
  protected readonly cEmail = signal('');
  protected readonly cTelefono = signal('');
  protected readonly cDireccion = signal('');
  protected readonly createSaving = signal(false);

  protected readonly editingId = signal<number | null>(null);
  protected readonly eNombre = signal('');
  protected readonly eTelefono = signal('');
  protected readonly eDireccion = signal('');
  protected readonly eEstado = signal('activo');
  protected readonly editSaving = signal(false);

  ngOnInit(): void {
    this.load();
  }

  protected search(): void {
    this.load();
  }

  protected openCreate(): void {
    this.cNombre.set('');
    this.cEmail.set('');
    this.cTelefono.set('');
    this.cDireccion.set('');
    this.error.set('');
    this.showCreateForm.set(true);
  }

  protected closeCreate(): void {
    this.showCreateForm.set(false);
  }

  protected async submitCreate(): Promise<void> {
    if (!this.cNombre() || !this.cEmail()) {
      this.error.set('Completa nombre y correo.');
      return;
    }

    this.error.set('');
    this.createSaving.set(true);
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/clientes`, {
          nombre: this.cNombre(),
          email: this.cEmail(),
          telefono: this.cTelefono() || null,
          direccion: this.cDireccion() || null,
        }),
      );
      this.showCreateForm.set(false);
      await this.load();
    } catch (err) {
      this.error.set(this.extractError(err));
    } finally {
      this.createSaving.set(false);
    }
  }

  protected editCliente(c: Cliente): void {
    this.editingId.set(c.id);
    this.eNombre.set(c.nombre);
    this.eTelefono.set(c.telefono ?? '');
    this.eDireccion.set(c.direccion ?? '');
    this.eEstado.set(c.estado);
    this.error.set('');
  }

  protected closeEdit(): void {
    this.editingId.set(null);
  }

  protected async submitEdit(): Promise<void> {
    const id = this.editingId();
    if (!id || !this.eNombre()) {
      this.error.set('El nombre no puede estar vacio.');
      return;
    }

    this.error.set('');
    this.editSaving.set(true);
    try {
      await firstValueFrom(
        this.http.put(`${environment.apiUrl}/clientes/${id}`, {
          nombre: this.eNombre(),
          telefono: this.eTelefono() || null,
          direccion: this.eDireccion() || null,
          estado: this.eEstado(),
        }),
      );
      this.editingId.set(null);
      await this.load();
    } catch (err) {
      this.error.set(this.extractError(err));
    } finally {
      this.editSaving.set(false);
    }
  }

  protected async toggleEstado(c: Cliente): Promise<void> {
    const nuevoEstado = c.estado === 'activo' ? 'inactivo' : 'activo';
    const accion = nuevoEstado === 'inactivo' ? 'desactivar' : 'activar';
    if (!confirm(`¿Seguro que quieres ${accion} a "${c.nombre}"?`)) return;

    try {
      await firstValueFrom(
        this.http.put(`${environment.apiUrl}/clientes/${c.id}`, {
          nombre: c.nombre,
          telefono: c.telefono,
          direccion: c.direccion,
          estado: nuevoEstado,
        }),
      );
      await this.load();
    } catch (err) {
      this.error.set(this.extractError(err));
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = {};
      if (this.buscar().trim()) params['buscar'] = this.buscar().trim();
      const empresa = this.empresaId();
      if (empresa !== null) params['empresa_id'] = String(empresa);

      const res = await firstValueFrom(this.http.get<Cliente[]>(`${environment.apiUrl}/clientes`, { params }));
      this.clientes.set(res);
    } catch {
      this.error.set('No se pudo cargar los clientes.');
    } finally {
      this.loading.set(false);
    }
  }

  // "7 compras · 1 reserva · 20 usos del probador" para la columna de relacion.
  protected relacion(c: Cliente): string[] {
    const r = c.relacion;
    const partes: string[] = [];
    const agregar = (n: number | undefined, uno: string, varios: string) => {
      if (n) partes.push(`${n} ${n === 1 ? uno : varios}`);
    };
    agregar(r?.compras, 'compra', 'compras');
    agregar(r?.reservas, 'reserva', 'reservas');
    if (r?.en_carrito) partes.push('Prendas en su carrito');
    agregar(r?.usos_probador, 'uso del probador', 'usos del probador');
    return partes.length ? partes : ['Registrado por la tienda'];
  }

  protected metodoLabel(metodo: string): string {
    const etiquetas: Record<string, string> = {
      email: 'Email',
      google: 'Google',
      admin: 'Admin',
      sistema: 'Sistema',
    };
    return etiquetas[metodo] ?? metodo;
  }

  private extractError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'Ocurrio un error inesperado.';
  }
}
