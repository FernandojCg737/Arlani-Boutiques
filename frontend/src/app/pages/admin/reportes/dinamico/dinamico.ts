import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../../environments/environment';
import { ReporteDinamico } from '../../../../components/reporte/reporte-dinamico';

// CU07: reporte dinámico de la tienda (el SuperAdministrador, de la tienda elegida).
@Component({
  selector: 'app-reporte-dinamico-page',
  imports: [RouterLink, ReporteDinamico],
  template: `
    <div class="reporte-page">
      <div class="reporte-toolbar">
        <a routerLink=".." queryParamsHandling="preserve" class="volver-link">← Volver a Reportes</a>
      </div>
      <h1 class="reporte-titulo">Reporte dinámico</h1>
      <p class="reporte-intro">Elige qué datos ver, cómo agruparlos y qué medir. Luego expórtalo o envíalo por correo.</p>
      <app-reporte-dinamico ambito="tienda" [sucursales]="sucursales()" />
    </div>
  `,
  styles: `
    .reporte-page {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }
    .volver-link {
      font-size: 13px;
      color: #1f2a44;
      text-decoration: none;
    }
    .reporte-titulo {
      margin: 14px 0 4px;
      font-size: 26px;
      font-weight: 800;
      text-transform: uppercase;
      color: #1f2a44;
    }
    .reporte-intro {
      margin: 0 0 18px;
      color: #666;
      font-size: 14px;
    }
  `,
})
export class ReporteDinamicoPage implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly sucursales = signal<{ id: number; nombre: string }[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      this.sucursales.set(
        await firstValueFrom(this.http.get<{ id: number; nombre: string }[]>(`${environment.apiUrl}/ventas/presencial/sucursales`)),
      );
    } catch {
      // Sin la lista, el filtro de sucursal no aparece (el reporte sale de todas).
    }
  }
}
