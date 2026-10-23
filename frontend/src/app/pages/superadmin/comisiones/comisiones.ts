import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { mensajeError } from '../../../services/plataforma';

interface ComisionTienda {
  empresa_id: number;
  nombre: string;
  subdominio: string;
  estado: string;
  plan_nombre: string | null;
  comision_pct: string | null;
  ventas: number;
  ventas_bob: string;
  comisiones_bob: string;
  pagado_bob: string;
  saldo_bob: string;
}

interface Liquidacion {
  id: number;
  empresa_nombre: string;
  fecha: string;
  paypal_order_id: string;
  bruto_bob: string;
  comision_bob: string;
  neto_bob: string;
  neto_usd: string;
  paypal_email: string;
  estado: 'pendiente' | 'enviada' | 'fallida';
  error: string | null;
}

function isoHoyBolivia(): string {
  // Fecha de hoy en La Paz (UTC-4), en formato del <input type="date">.
  return new Date(Date.now() - 4 * 3600 * 1000).toISOString().slice(0, 10);
}

// CU10 (comisiones): lo que gana Arlani por las ventas en linea de cada
// tienda en un periodo, lo que cada tienda ya pago y lo que debe hoy.
@Component({
  selector: 'app-superadmin-comisiones',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './comisiones.html',
  styleUrl: './comisiones.scss',
})
export class SuperadminComisiones implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly hasta = signal(isoHoyBolivia());
  protected readonly desde = signal(isoHoyBolivia().slice(0, 8) + '01');
  protected readonly filas = signal<ComisionTienda[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly soloConMovimiento = signal(true);

  protected readonly visibles = computed(() =>
    this.soloConMovimiento()
      ? this.filas().filter((f) => f.ventas > 0 || Number(f.saldo_bob) !== 0 || Number(f.pagado_bob) > 0)
      : this.filas(),
  );

  protected readonly totales = computed(() =>
    this.filas().reduce(
      (t, f) => ({
        ventas: t.ventas + f.ventas,
        vendido: t.vendido + Number(f.ventas_bob),
        comisiones: t.comisiones + Number(f.comisiones_bob),
        pagado: t.pagado + Number(f.pagado_bob),
        porCobrar: t.porCobrar + Math.max(0, Number(f.saldo_bob)),
      }),
      { ventas: 0, vendido: 0, comisiones: 0, pagado: 0, porCobrar: 0 },
    ),
  );

  // Envios a cada tienda por las compras con "Pagar todo".
  protected readonly liquidaciones = signal<Liquidacion[]>([]);
  protected readonly reintentando = signal<number | null>(null);

  ngOnInit(): void {
    void this.cargar();
    void this.cargarLiquidaciones();
  }

  private async cargarLiquidaciones(): Promise<void> {
    try {
      this.liquidaciones.set(
        await firstValueFrom(this.http.get<Liquidacion[]>(`${environment.apiUrl}/plataforma/liquidaciones`)),
      );
    } catch {
      this.liquidaciones.set([]);
    }
  }

  protected async reintentar(l: Liquidacion): Promise<void> {
    this.reintentando.set(l.id);
    this.error.set('');
    try {
      const nueva = await firstValueFrom(
        this.http.post<Liquidacion>(`${environment.apiUrl}/plataforma/liquidaciones/${l.id}/reintentar`, {}),
      );
      this.liquidaciones.update((ls) => ls.map((x) => (x.id === nueva.id ? nueva : x)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos reintentar el envío.'));
    } finally {
      this.reintentando.set(null);
    }
  }

  protected cambiarFecha(campo: 'desde' | 'hasta', valor: string): void {
    if (!valor) return;
    this[campo].set(valor);
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set('');
    try {
      this.filas.set(
        await firstValueFrom(
          this.http.get<ComisionTienda[]>(`${environment.apiUrl}/plataforma/comisiones`, {
            params: { desde: this.desde(), hasta: this.hasta() },
          }),
        ),
      );
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar las comisiones.'));
    } finally {
      this.cargando.set(false);
    }
  }
}
