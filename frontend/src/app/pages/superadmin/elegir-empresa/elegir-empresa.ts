import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../../environments/environment';
import { EmpresaTenant, PlataformaApi, mensajeError } from '../../../services/plataforma';
import { AdminClientes } from '../../admin/clientes/clientes';
import { buscarCaso } from '../superadmin-menu';

// 1er parcial: antes de abrir un CU, el SuperAdministrador elige la empresa
// (tenant) sobre la que va a trabajar. Cada empresa es un cuadro.
@Component({
  selector: 'app-superadmin-elegir-empresa',
  imports: [AdminClientes],
  templateUrl: './elegir-empresa.html',
  styleUrl: './elegir-empresa.scss',
})
export class SuperadminElegirEmpresa {
  private readonly api = inject(PlataformaApi);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly codigo = toSignal(this.route.paramMap.pipe(map((p) => p.get('codigo') ?? '')), {
    initialValue: '',
  });
  protected readonly ubicacion = computed(() => buscarCaso('p1', this.codigo()));

  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly empresas = signal<EmpresaTenant[]>([]);
  protected readonly busqueda = signal('');
  // CU03: cuantos clientes trabajaron con cada empresa.
  protected readonly clientes = signal<Record<number, number>>({});

  protected readonly visibles = computed(() => {
    const q = this.busqueda().trim().toLowerCase();
    return this.empresas().filter((e) => !q || e.nombre.toLowerCase().includes(q) || e.subdominio.includes(q));
  });

  constructor() {
    void this.cargar();
    void this.cargarClientes();
  }

  private async cargarClientes(): Promise<void> {
    try {
      const filas = await firstValueFrom(
        this.http.get<{ empresa_id: number; total: number }[]>(`${environment.apiUrl}/clientes/por-empresa`),
      );
      this.clientes.set(Object.fromEntries(filas.map((f) => [f.empresa_id, f.total])));
    } catch {
      // el conteo es un dato extra: sin el, los cuadros siguen igual
    }
  }

  private async cargar(): Promise<void> {
    try {
      this.empresas.set(await this.api.empresas());
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar las empresas.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected abrir(e: EmpresaTenant): void {
    const ruta = this.ubicacion()?.caso.ruta;
    if (ruta) void this.router.navigate(['/superadmin', ruta], { queryParams: { empresa: e.id } });
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }
}
