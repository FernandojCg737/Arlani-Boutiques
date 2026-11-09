import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { AppChart } from '../../../components/chart/chart';

interface DistribucionEstrellas {
  estrellas: number;
  cantidad: number;
}

interface CalificacionResumen {
  promedio: number;
  total: number;
  distribucion: DistribucionEstrellas[];
}

interface CalificacionItem {
  // Numero propio de la tienda (#1, #2...): el que se muestra.
  venta_numero?: number | null;
  id: number;
  venta_id: number;
  estrellas: number;
  comentario: string | null;
  fecha: string;
  cliente_nombre: string;
  cliente_email: string;
  sucursal_nombre: string;
  empleado_nombre: string | null;
}

interface CalificacionPage {
  resumen: CalificacionResumen;
  items: CalificacionItem[];
  total: number;
  page: number;
  page_size: number;
}

// CU20 "Reputacion y Calificaciones": panel de solo lectura -- promedio
// general (calculado sobre TODAS las calificaciones, sin importar el
// filtro de la tabla), desglose por estrellas, y el detalle de quien
// califico que compra, cuando y con que comentario.
@Component({
  selector: 'app-admin-calificaciones',
  imports: [DatePipe, DecimalPipe, AppChart],
  templateUrl: './calificaciones.html',
  styleUrl: './calificaciones.scss',
})
export class AdminCalificaciones implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly resumen = signal<CalificacionResumen | null>(null);
  protected readonly items = signal<CalificacionItem[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 20;
  protected readonly filtroEstrellas = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  protected get totalPages(): number {
    return Math.max(1, Math.ceil(this.total() / this.pageSize));
  }

  protected labelsDistribucion(): string[] {
    return (this.resumen()?.distribucion ?? []).map((d) => `${d.estrellas} estrella${d.estrellas === 1 ? '' : 's'}`);
  }

  protected dataDistribucion(): number[] {
    return (this.resumen()?.distribucion ?? []).map((d) => d.cantidad);
  }

  ngOnInit(): void {
    void this.load();
  }

  protected filtrar(): void {
    this.page.set(1);
    void this.load();
  }

  protected goToPage(page: number): void {
    if (page < 1 || page > this.totalPages) return;
    this.page.set(page);
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = { page: String(this.page()), page_size: String(this.pageSize) };
      if (this.filtroEstrellas()) params['estrellas'] = this.filtroEstrellas();

      const res = await firstValueFrom(
        this.http.get<CalificacionPage>(`${environment.apiUrl}/calificaciones`, { params }),
      );
      this.resumen.set(res.resumen);
      this.items.set(res.items);
      this.total.set(res.total);
    } catch {
      this.error.set('No se pudo cargar las calificaciones.');
    } finally {
      this.loading.set(false);
    }
  }
}
