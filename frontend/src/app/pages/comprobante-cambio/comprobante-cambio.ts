import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { colorParaTextoBlanco } from '../../services/marca-tienda';
import { CambioPrenda, DESTINO_PRENDA, ESTADO_CAMBIO, MOTIVO_CAMBIO } from '../admin/cambios/cambios';
import { TiendaFactura } from '../comprobante/comprobante';

interface CambioConTienda extends CambioPrenda {
  tienda: TiendaFactura;
}

// Comprobante de un cambio de prenda: mismo diseño que la factura de la
// venta, con el logo, el color y los datos de la tienda. Lo ve el cliente
// (/mis-cambios/:id) y el personal (/admin/cambio/:id).
@Component({
  selector: 'app-comprobante-cambio',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './comprobante-cambio.html',
  styleUrls: ['../comprobante/comprobante.scss', './comprobante-cambio.scss'],
})
export class ComprobanteCambio implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly http = inject(HttpClient);

  protected readonly cambio = signal<CambioConTienda | undefined>(undefined);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly esPersonal = this.route.snapshot.data['modo'] === 'admin';
  protected readonly estadoLabel = ESTADO_CAMBIO;
  protected readonly motivoLabel = MOTIVO_CAMBIO;
  protected readonly destinoLabel = DESTINO_PRENDA;

  protected readonly color = computed(() => {
    const t = this.cambio()?.tienda;
    return t ? colorParaTextoBlanco(t.color_marca) : null;
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.error.set('Cambio no encontrado.');
      this.cargando.set(false);
      return;
    }
    void this.cargar(id);
  }

  private async cargar(id: string): Promise<void> {
    const ruta = this.esPersonal ? `cambios/${id}` : `cambios/mios/${id}`;
    try {
      this.cambio.set(await firstValueFrom(this.http.get<CambioConTienda>(`${environment.apiUrl}/${ruta}`)));
    } catch {
      this.error.set('No pudimos encontrar ese cambio.');
    } finally {
      this.cargando.set(false);
    }
  }

  protected numero(valor: string): number {
    return Number(valor);
  }

  protected folio(id: number): string {
    return 'C-' + String(id).padStart(6, '0');
  }

  protected imprimir(): void {
    window.print();
  }
}
