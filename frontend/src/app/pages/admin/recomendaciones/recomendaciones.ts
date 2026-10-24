import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';

interface RecomendacionItem {
  id: number;
  cliente_nombre: string;
  cliente_email: string;
  producto_nombre: string;
  score: string;
  origen: string;
  razon: string | null;
  convertido: boolean;
  fecha: string;
}

interface RecomendacionPage {
  resumen: { total_activas: number; convertidas: number; tasa_conversion: number };
  items: RecomendacionItem[];
  total: number;
  page: number;
  page_size: number;
}

interface RelacionadoItem {
  id: number;
  producto_nombre: string;
  relacionado_nombre: string;
  score: string;
  origen: string;
  razon: string | null;
  fecha: string;
}

interface RelacionadoPage {
  resumen: { productos_totales: number; productos_cubiertos: number; cobertura_pct: number };
  items: RelacionadoItem[];
  total: number;
  page: number;
  page_size: number;
}

const ORIGEN_LABEL: Record<string, string> = {
  modelo_ml: 'Modelo de ML (híbrido)',
  compra_conjunta: 'Comprado junto a...',
  similar_categoria: 'Similar a tus compras',
  mas_vendido: 'Mas vendido',
};

const ORIGEN_LABEL_RELACIONADOS: Record<string, string> = {
  modelo_ml: 'Modelo de ML (híbrido)',
  vistos_juntos: 'Vistos juntos',
  similar_categoria: 'Misma categoria/marca',
  mas_vendido: 'Mas vendido',
  catalogo_general: 'Catalogo general (respaldo)',
};

// CU18 "Recomendar Prendas por IA": panel de solo lectura -- el ranking lo
// arma el modelo de recomendacion de cada tienda (con las reglas en SQL de
// respaldo: compra conjunta / similares / mas vendidos) y Gemini redacta la
// razon de cada una; aca solo se audita a
// quien se le recomendo que, y si esa recomendacion termino en una compra
// real (convertido, marcado solo por un trigger cuando el cliente compra).
@Component({
  selector: 'app-admin-recomendaciones',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './recomendaciones.html',
  styleUrl: './recomendaciones.scss',
})
export class AdminRecomendaciones implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly resumen = signal<RecomendacionPage['resumen'] | null>(null);
  protected readonly items = signal<RecomendacionItem[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly pageSize = 20;
  protected readonly filtroOrigen = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly origenLabel = ORIGEN_LABEL;

  protected readonly resumenRel = signal<RelacionadoPage['resumen'] | null>(null);
  protected readonly itemsRel = signal<RelacionadoItem[]>([]);
  protected readonly totalRel = signal(0);
  protected readonly pageRel = signal(1);
  protected readonly filtroOrigenRel = signal('');
  protected readonly loadingRel = signal(false);
  protected readonly errorRel = signal('');
  protected readonly origenLabelRel = ORIGEN_LABEL_RELACIONADOS;

  protected get totalPages(): number {
    return Math.max(1, Math.ceil(this.total() / this.pageSize));
  }

  protected get totalPagesRel(): number {
    return Math.max(1, Math.ceil(this.totalRel() / this.pageSize));
  }

  ngOnInit(): void {
    void this.load();
    void this.loadRelacionados();
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

  protected filtrarRelacionados(): void {
    this.pageRel.set(1);
    void this.loadRelacionados();
  }

  protected goToPageRelacionados(page: number): void {
    if (page < 1 || page > this.totalPagesRel) return;
    this.pageRel.set(page);
    void this.loadRelacionados();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = { page: String(this.page()), page_size: String(this.pageSize) };
      if (this.filtroOrigen()) params['origen'] = this.filtroOrigen();

      const res = await firstValueFrom(
        this.http.get<RecomendacionPage>(`${environment.apiUrl}/recomendaciones`, { params }),
      );
      this.resumen.set(res.resumen);
      this.items.set(res.items);
      this.total.set(res.total);
    } catch {
      this.error.set('No se pudo cargar las recomendaciones.');
    } finally {
      this.loading.set(false);
    }
  }

  private async loadRelacionados(): Promise<void> {
    this.loadingRel.set(true);
    this.errorRel.set('');
    try {
      const params: Record<string, string> = { page: String(this.pageRel()), page_size: String(this.pageSize) };
      if (this.filtroOrigenRel()) params['origen'] = this.filtroOrigenRel();

      const res = await firstValueFrom(
        this.http.get<RelacionadoPage>(`${environment.apiUrl}/recomendaciones/relacionados-admin`, { params }),
      );
      this.resumenRel.set(res.resumen);
      this.itemsRel.set(res.items);
      this.totalRel.set(res.total);
    } catch {
      this.errorRel.set('No se pudo cargar "Tambien te puede interesar".');
    } finally {
      this.loadingRel.set(false);
    }
  }
}
