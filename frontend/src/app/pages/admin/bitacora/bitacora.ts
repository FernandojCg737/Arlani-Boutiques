import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import { EmpresaTenant, PlataformaApi } from '../../../services/plataforma';

interface BitacoraItem {
  id: number;
  usuario_id: number;
  usuario_nombre: string;
  usuario_email: string;
  accion: string;
  entidad_afectada: string;
  entidad_id: number | null;
  fecha: string;
  detalle: string | null;
  ip_address: string | null;
  plataforma: string | null;
  empresa_id: number | null;
  empresa_nombre: string | null;
}

// SuperAdministrador: todo, solo lo de la plataforma o una empresa.
type FiltroBitacora = 'todas' | 'plataforma' | number;

interface BitacoraPage {
  items: BitacoraItem[];
  total: number;
  page: number;
  page_size: number;
}

@Component({
  selector: 'app-admin-bitacora',
  imports: [DatePipe],
  templateUrl: './bitacora.html',
  styleUrl: './bitacora.scss',
})
// CU08 Auditar operaciones. Cada tienda ve solo los registros que se
// refieren a ella; el SuperAdministrador ve todo y filtra por empresa.
export class AdminBitacora implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly plataforma = inject(PlataformaApi);
  protected readonly esSuper = inject(Auth).isSuperAdmin();

  protected readonly empresas = signal<EmpresaTenant[]>([]);
  protected readonly filtro = signal<FiltroBitacora>('todas');

  protected readonly items = signal<BitacoraItem[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 20;
  protected readonly buscar = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  protected get totalPages(): number {
    return Math.max(1, Math.ceil(this.total() / this.pageSize));
  }

  ngOnInit(): void {
    this.load();
    if (this.esSuper) void this.cargarEmpresas();
  }

  protected elegirFiltro(f: FiltroBitacora): void {
    this.filtro.set(f);
    this.page.set(1);
    this.load();
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  private async cargarEmpresas(): Promise<void> {
    try {
      this.empresas.set(await this.plataforma.empresas());
    } catch {
      // sin la lista igual se ve "Todo" y "Plataforma"
    }
  }

  protected search(): void {
    this.page.set(1);
    this.load();
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.totalPages) return;
    this.page.set(page);
    this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = {
        page: String(this.page()),
        page_size: String(this.pageSize),
      };
      if (this.buscar().trim()) params['buscar'] = this.buscar().trim();
      const f = this.filtro();
      if (this.esSuper && typeof f === 'number') params['empresa_id'] = String(f);
      if (this.esSuper && f === 'plataforma') params['plataforma'] = 'true';

      const res = await firstValueFrom(this.http.get<BitacoraPage>(`${environment.apiUrl}/bitacora`, { params }));
      this.items.set(res.items);
      this.total.set(res.total);
    } catch {
      this.error.set('No se pudo cargar la bitacora.');
    } finally {
      this.loading.set(false);
    }
  }
}
