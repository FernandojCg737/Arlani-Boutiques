import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { Periodo } from '../data/planes';

export interface SolicitudSuscripcion {
  plan: string;
  periodo: Periodo;
  boutique: {
    nombre: string;
    subdominio: string;
    ciudad: string;
    sucursales: number;
    color: string;
  };
  // Usuario con el que la boutique entra a su panel. Las credenciales llegan
  // al correo de la cuenta del cliente que compra.
  administrador: {
    nombre: string;
    email: string;
  };
}

export interface Cotizacion {
  plan_codigo: string;
  plan_nombre: string;
  periodo: string;
  max_sucursales: number;
  monto_bob: string;
  tipo_cambio: string;
  monto_usd: string;
  requiere_pago: boolean;
  subdominio: string;
}

export interface SuscripcionCreada {
  empresa_id: number;
  empresa_nombre: string;
  subdominio: string;
  plan_nombre: string;
  admin_email: string;
  correo_destino: string;
  metodo: 'paypal' | 'prueba';
  monto_bob: string;
  monto_usd: string;
  logo_guardado: boolean;
  correo_enviado: boolean;
}

// Compra de la suscripción de una boutique (/empezar): se cotiza y valida
// antes de cobrar, se paga con PayPal (en USD) y recién ahí el backend crea
// la empresa, su suscripción y su Administrador. La prueba no pasa por PayPal.
@Injectable({ providedIn: 'root' })
export class RegistroEmpresaApi {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/empresas/registro`;

  cotizar(datos: SolicitudSuscripcion): Promise<Cotizacion> {
    return firstValueFrom(this.http.post<Cotizacion>(`${this.base}/cotizar`, datos));
  }

  async crearOrden(datos: SolicitudSuscripcion): Promise<string> {
    const res = await firstValueFrom(this.http.post<{ order_id: string }>(`${this.base}/orden`, datos));
    return res.order_id;
  }

  // orderId: la orden de PayPal ya aprobada (null en la prueba). logo: data URL.
  confirmar(datos: SolicitudSuscripcion, orderId: string | null, logo: string | null): Promise<SuscripcionCreada> {
    return firstValueFrom(
      this.http.post<SuscripcionCreada>(`${this.base}/confirmar`, { ...datos, order_id: orderId, logo }),
    );
  }
}
