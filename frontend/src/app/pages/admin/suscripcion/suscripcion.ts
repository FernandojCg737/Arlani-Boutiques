import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { enlaceTienda, mensajeError, rutaTienda } from '../../../services/plataforma';

interface PlanDisponible {
  codigo: string;
  nombre: string;
  precio_mensual: string;
  max_sucursales: number;
  dias_prueba: number | null;
  ia_generativa: boolean;
}

interface HistorialSuscripcion {
  id: number;
  plan_nombre: string;
  periodo: string;
  monto: string;
  fecha_inicio: string;
  fecha_fin: string | null;
  estado: string;
}

interface MiSuscripcion {
  empresa_id: number;
  empresa_nombre: string;
  subdominio: string;
  color_marca: string;
  empresa_estado: 'activa' | 'suspendida';
  plan_codigo: string | null;
  plan_nombre: string | null;
  precio_mensual: string | null;
  ia_generativa: boolean | null;
  periodo: 'mensual' | 'anual' | 'prueba' | null;
  monto: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  dias_restantes: number | null;
  sucursales_usadas: number;
  max_sucursales: number | null;
  personal: number;
  clientes: number;
  historial: HistorialSuscripcion[];
  planes: PlanDisponible[];
}

// Soporte de Arlani: los cambios de plan los aplica el SuperAdministrador.
const WHATSAPP_SOPORTE = '59173766956';
const AVISO_DIAS = 15;

// Mi suscripcion: el Administrador de la tienda ve su plan, cuando vence,
// cuanto usa de el, el enlace de su tienda y los planes a los que puede pasar.
@Component({
  selector: 'app-admin-suscripcion',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './suscripcion.html',
  styleUrl: './suscripcion.scss',
})
export class AdminSuscripcion {
  private readonly http = inject(HttpClient);

  protected readonly datos = signal<MiSuscripcion | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly copiado = signal(false);

  protected readonly textoPeriodo: Record<string, string> = {
    mensual: 'Pago mensual',
    anual: 'Pago anual',
    prueba: 'Periodo de prueba',
  };
  protected readonly textoEstado: Record<string, string> = {
    activa: 'Vigente',
    reemplazada: 'Reemplazada',
    cancelada: 'Cancelada',
    vencida: 'Vencida',
  };

  protected readonly enlace = computed(() => {
    const d = this.datos();
    return d ? enlaceTienda(d.subdominio) : '';
  });
  protected readonly ruta = computed(() => {
    const d = this.datos();
    return d ? rutaTienda(d.subdominio) : '/';
  });

  // Uso de sucursales (0-100) para la barra.
  protected readonly usoSucursales = computed(() => {
    const d = this.datos();
    if (!d?.max_sucursales) return 0;
    return Math.min(100, Math.round((d.sucursales_usadas / d.max_sucursales) * 100));
  });

  // Aviso arriba: suspendida, sin plan, vencida o por vencer.
  protected readonly aviso = computed<{ tono: 'alerta' | 'info'; texto: string } | null>(() => {
    const d = this.datos();
    if (!d) return null;
    if (d.empresa_estado === 'suspendida')
      return { tono: 'alerta', texto: 'Tu tienda está suspendida. Escríbenos a soporte para reactivarla.' };
    if (!d.plan_codigo) return { tono: 'alerta', texto: 'Tu tienda no tiene una suscripción vigente.' };
    const dias = d.dias_restantes;
    if (dias !== null && dias < 0)
      return { tono: 'alerta', texto: 'Tu suscripción venció. Renuévala para seguir vendiendo sin cortes.' };
    if (dias !== null && dias <= AVISO_DIAS)
      return {
        tono: 'info',
        texto:
          dias === 0
            ? 'Tu suscripción vence hoy.'
            : `Tu suscripción vence en ${dias} ${dias === 1 ? 'día' : 'días'}.`,
      };
    return null;
  });

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      this.datos.set(
        await firstValueFrom(this.http.get<MiSuscripcion>(`${environment.apiUrl}/mi-empresa/suscripcion`)),
      );
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar tu suscripción.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected async copiarEnlace(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.enlace());
      this.copiado.set(true);
      setTimeout(() => this.copiado.set(false), 2000);
    } catch {
      // sin portapapeles (http sin permisos): el enlace igual se puede seleccionar
    }
  }

  // Un plan mas chico no alcanza si ya tiene mas sucursales activas.
  protected noAlcanza(p: PlanDisponible): boolean {
    return (this.datos()?.sucursales_usadas ?? 0) > p.max_sucursales;
  }

  protected esMejora(p: PlanDisponible): boolean {
    return Number(p.precio_mensual) > Number(this.datos()?.precio_mensual ?? 0);
  }

  // El cambio lo aplica soporte: se abre WhatsApp con el pedido ya escrito.
  protected enlaceCambio(p: PlanDisponible | null): string {
    const d = this.datos();
    if (!d) return '#';
    const texto = p
      ? `Hola, soy el administrador de ${d.empresa_nombre} (${d.subdominio}). ` +
        `Quiero cambiar mi plan ${d.plan_nombre ?? 'actual'} al plan ${p.nombre}.`
      : `Hola, soy el administrador de ${d.empresa_nombre} (${d.subdominio}). Necesito ayuda con mi suscripción.`;
    return `https://wa.me/${WHATSAPP_SOPORTE}?text=${encodeURIComponent(texto)}`;
  }
}
