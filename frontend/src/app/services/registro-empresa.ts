import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { Periodo } from '../data/planes';

export interface RegistroEmpresaPayload {
  plan: string;
  periodo: Periodo;
  boutique: {
    nombre: string;
    subdominio: string;
    ciudad: string;
    sucursales: number;
    color: string;
  };
}

// Alta de una boutique nueva (empresa / tenant) en la plataforma. El dueño es
// el usuario con sesión iniciada: el backend lo toma del token.
// TODO: el endpoint POST /empresas/registro llega con el módulo multiempresa
// del backend (iteración del SaaS); hasta entonces la pantalla /empezar
// muestra el error de "no pudimos crear tu boutique".
@Injectable({ providedIn: 'root' })
export class RegistroEmpresaApi {
  private readonly http = inject(HttpClient);

  // Devuelve el enlace con el que quedo (con numero si el pedido ya existia).
  async registrar(datos: RegistroEmpresaPayload): Promise<{ id: number; subdominio: string }> {
    return firstValueFrom(
      this.http.post<{ id: number; subdominio: string }>(`${environment.apiUrl}/empresas/registro`, datos),
    );
  }
}
