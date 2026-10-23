import { HttpClient } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Auth } from '../auth';
import { Sincronizacion } from './sincronizacion';

interface CompraResumen {
  uuid: string;
  estado: 'por_pagar' | 'sin_stock';
  tienda: string;
  total_actual: string;
  precio_cambio: boolean;
  sin_stock: boolean;
}

const POSPUESTO = 'arlani_compras_pospuestas';

// Compras que el cliente hizo sin conexión y esperan su pago. Se consulta al
// servidor (vale para las hechas en la web o en la app móvil) al iniciar
// sesión, al volver la conexión y después de cada sincronización; si hay,
// la app muestra el aviso con prioridad (components/aviso-compras).
@Injectable({ providedIn: 'root' })
export class ComprasPorPagar {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly sync = inject(Sincronizacion);

  readonly compras = signal<CompraResumen[]>([]);
  readonly pospuesto = signal(this.leerPospuesto());
  readonly porPagar = computed(() => this.compras().filter((c) => c.estado === 'por_pagar').length);
  // El aviso se vuelve a mostrar si aparece una compra nueva.
  readonly mostrarAviso = computed(() => {
    const claves = this.compras().map((c) => c.uuid).sort().join(',');
    return claves !== '' && claves !== this.pospuesto();
  });

  constructor() {
    effect(() => {
      // Depende del usuario, de la conexión y de cada sincronización terminada.
      const usuario = this.auth.currentUser();
      const enLinea = this.sync.enLinea();
      this.sync.sincronizaciones();
      if (usuario?.tipo === 'cliente' && enLinea) void this.revisar();
      else if (usuario?.tipo !== 'cliente') this.compras.set([]);
    });
  }

  async revisar(): Promise<void> {
    if (this.auth.currentUser()?.tipo !== 'cliente' || !navigator.onLine) return;
    try {
      this.compras.set(await firstValueFrom(this.http.get<CompraResumen[]>(`${environment.apiUrl}/offline/pedidos`)));
    } catch {
      // Sin respuesta: se vuelve a revisar en la próxima sincronización.
    }
  }

  posponer(): void {
    const claves = this.compras().map((c) => c.uuid).sort().join(',');
    this.pospuesto.set(claves);
    try {
      sessionStorage.setItem(POSPUESTO, claves);
    } catch {
      // Sin sessionStorage: se pospone solo en esta pestaña.
    }
  }

  private leerPospuesto(): string {
    try {
      return sessionStorage.getItem(POSPUESTO) ?? '';
    } catch {
      return '';
    }
  }
}
