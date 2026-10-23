import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { mensajeError } from '../../../services/plataforma';

interface Resumen {
  descargas_30d: number;
  usuarios_con_datos: number;
  ultima_descarga: string | null;
  operaciones: number;
  confirmadas: number;
  conflictos: number;
  resueltas: number;
  anuladas: number;
  rechazadas: number;
  reenvios: number;
  ultima_sincronizacion: string | null;
}

interface Descarga {
  fecha: string;
  tipo: 'personal' | 'cliente';
  productos: number;
  clientes: number;
  usuario_nombre: string | null;
  usuario_tipo: string | null;
  sucursal_nombre: string | null;
}

interface UsuarioOffline {
  usuario_nombre: string;
  usuario_tipo: string;
  sucursal_nombre: string | null;
  operaciones: number;
  confirmadas: number;
  conflictos: number;
  resueltas: number;
  no_registradas: number;
  reenvios: number;
  ultima_sincronizacion: string | null;
  ultima_descarga: string | null;
  descargas: number;
}

interface Seguimiento {
  plan: string | null;
  plan_offline: boolean;
  resumen: Resumen;
  descargas: Descarga[];
  usuarios: UsuarioOffline[];
}

const TIPO_USUARIO: Record<string, string> = {
  administrador: 'Administrador',
  encargado_sucursal: 'Encargado',
  cajero: 'Cajero',
  cliente: 'Cliente',
};

// Seguimiento de una tienda sin conexión (SuperAdministrador, por tienda):
// CU11 quién descargó datos a su dispositivo y de cuándo son; CU12 cómo
// sincroniza cada usuario (confirmadas, conflictos, reenvíos).
@Component({
  selector: 'app-seguimiento-offline',
  imports: [DatePipe, RouterLink],
  templateUrl: './seguimiento-offline.html',
  styleUrls: ['../../admin/ventas/ventas.scss', '../../admin/sin-conexion/sin-conexion.scss', './seguimiento-offline.scss'],
})
export class SeguimientoOffline implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);

  protected readonly tipoUsuario = TIPO_USUARIO;
  protected readonly vista = signal<'descargas' | 'sincronizacion'>(this.route.snapshot.data['vista'] ?? 'descargas');
  protected readonly empresa = this.route.snapshot.queryParamMap.get('empresa');
  protected readonly datos = signal<Seguimiento | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');

  ngOnInit(): void {
    void this.cargar();
  }

  protected async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set('');
    try {
      this.datos.set(await firstValueFrom(this.http.get<Seguimiento>(`${environment.apiUrl}/offline/seguimiento`)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar el seguimiento sin conexión.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected hace(fecha: string | null): string {
    if (!fecha) return 'nunca';
    const min = Math.round((Date.now() - new Date(fecha).getTime()) / 60_000);
    if (min < 60) return min < 1 ? 'hace un momento' : `hace ${min} min`;
    const h = Math.round(min / 60);
    return h < 48 ? `hace ${h} h` : `hace ${Math.round(h / 24)} días`;
  }

  // Datos descargados hace más de un día: lo que ven puede estar viejo.
  protected viejo(fecha: string | null): boolean {
    return !!fecha && Date.now() - new Date(fecha).getTime() > 24 * 3_600_000;
  }
}
