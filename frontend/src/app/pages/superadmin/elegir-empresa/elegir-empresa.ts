import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../../../environments/environment';
import { EmpresaTenant, PlataformaApi, mensajeError } from '../../../services/plataforma';
import { AdminClientes } from '../../admin/clientes/clientes';
import { ParcialId, buscarCaso } from '../superadmin-menu';

// Antes de abrir un CU por empresa, el SuperAdministrador elige la empresa
// (tenant) sobre la que va a trabajar. Cada empresa es un cuadro. Sirve a los
// CUs del 1er parcial (/empresa/:codigo) y del 2do (/tiendas/:codigo: CU03
// sucursales y CU04 catalogo, que luego muestran solo lo de esa tienda).
@Component({
  selector: 'app-superadmin-elegir-empresa',
  imports: [AdminClientes, RouterLink],
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
  private readonly parcial: ParcialId = this.route.snapshot.data['parcial'] ?? 'p1';
  protected readonly ubicacion = computed(() => buscarCaso(this.parcial, this.codigo()));
  // CU03 del 1er parcial (clientes): debajo de las empresas van todos.
  protected readonly esClientes = computed(() => this.parcial === 'p1' && this.codigo() === 'CU03');

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
    const caso = this.ubicacion()?.caso;
    // Si se llego desde una pestana (ej. Inventario del CU04), vuelve a ella.
    const destino = this.route.snapshot.queryParamMap.get('destino');
    const pestanas = [caso?.ruta, ...(caso?.subs ?? []).map((s) => s.ruta)];
    const ruta = destino && pestanas.includes(destino) ? destino : caso?.ruta;
    if (ruta) void this.router.navigate(['/superadmin', ruta], { queryParams: { empresa: e.id } });
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }
}
