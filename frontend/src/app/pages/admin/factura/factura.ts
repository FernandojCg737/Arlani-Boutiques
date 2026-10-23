import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { colorParaTextoBlanco } from '../../../services/marca-tienda';
import { ESTADO_PAGO_LABEL, METODO_LABEL, TiendaFactura } from '../../comprobante/comprobante';

interface DetalleVenta {
  id: number;
  producto_nombre: string;
  talla_codigo: string;
  color_nombre: string;
  cantidad: number;
  precio_unitario: string;
}

interface VentaAdmin {
  id: number;
  tipo: string;
  sucursal_nombre: string;
  fecha: string;
  total: string;
  estado: string;
  metodo_pago: string;
  metodo_pago_nombre: string | null;
  estado_pago: string;
  cliente_nombre: string;
  cliente_email: string;
  atendido_por_nombre: string | null;
  tienda: TiendaFactura | null;
  detalles: DetalleVenta[];
}

// CU11: factura/comprobante de una venta cualquiera (no solo las propias),
// para que el staff pueda verla o "descargarla" (imprimir a PDF) desde el
// panel de Gestion de Ventas. Solo tiene sentido para ventas ya completadas
// -- el boton que lleva aca en el panel ya filtra por eso.
@Component({
  selector: 'app-admin-factura',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './factura.html',
  styleUrl: './factura.scss',
})
export class AdminFactura implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly http = inject(HttpClient);

  protected readonly venta = signal<VentaAdmin | undefined>(undefined);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly metodoLabel = METODO_LABEL;
  protected readonly estadoLabel = ESTADO_PAGO_LABEL;

  // Logo, color y datos fiscales de la tienda que emite el comprobante
  // (vienen con la venta: cada tienda factura solo lo suyo).
  protected readonly color = computed(() => {
    const t = this.venta()?.tienda;
    return t ? colorParaTextoBlanco(t.color_marca) : null;
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.error.set('Venta no encontrada.');
      this.cargando.set(false);
      return;
    }
    void this.cargar(id);
  }

  private async cargar(id: string): Promise<void> {
    try {
      const res = await firstValueFrom(this.http.get<VentaAdmin>(`${environment.apiUrl}/ventas/${id}`));
      this.venta.set(res);
    } catch {
      this.error.set('No pudimos encontrar esa venta.');
    } finally {
      this.cargando.set(false);
    }
  }

  protected folio(id: number): string {
    return String(id).padStart(6, '0');
  }

  protected subtotal(d: DetalleVenta): number {
    return Number(d.precio_unitario) * d.cantidad;
  }

  protected imprimir(): void {
    window.print();
  }
}
