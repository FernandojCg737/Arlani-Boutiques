import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { Auth } from '../../../services/auth';
import { mensajeError } from '../../../services/plataforma';
import { ESTADO_OPERACION } from '../sin-conexion/sin-conexion';

interface ItemOperacion {
  producto_id: number;
  talla_id: number;
  color_id: number;
  cantidad: number;
  precio: string;
  producto: string;
  talla: string;
  color: string;
}

interface ItemConflicto {
  producto_id: number;
  producto: string;
  talla_id: number;
  talla: string;
  color_id: number;
  color: string;
  pedido: number;
  disponible: number;
}

export interface OperacionServidor {
  id: number;
  uuid: string;
  tipo: 'venta' | 'reserva';
  estado: string;
  mensaje: string | null;
  sucursal_nombre: string | null;
  usuario_nombre: string | null;
  usuario_tipo: string | null;
  cliente_nombre: string | null;
  registrada_en: string;
  recibida_en: string;
  intentos: number;
  total: string;
  items: ItemOperacion[];
  conflicto: ItemConflicto[] | null;
  venta_id: number | null;
  reserva_id: number | null;
  resuelta_por_nombre: string | null;
  resuelta_en: string | null;
  resolucion: string | null;
}

interface Disponible {
  producto_id: number;
  talla_id: number;
  talla: string;
  color_id: number;
  color: string;
  stock: number;
}

// Una línea del ajuste: la variante elegida (o "" = quitar la prenda) y cuántas.
interface LineaAjuste {
  item: ItemOperacion;
  variante: string;
  cantidad: number;
}

const TIPO_USUARIO: Record<string, string> = {
  administrador: 'Administrador',
  encargado_sucursal: 'Encargado',
  cajero: 'Cajero',
  cliente: 'Cliente (app)',
};

// CU13 (servidor) y CU14 Gestionar conflictos de sincronización: lo que
// llegó de los dispositivos sin conexión y, si al llegar ya no había stock,
// el conflicto para que el Administrador o el Encargado lo ajuste (otra
// talla, color o cantidad) o lo anule. El SuperAdministrador solo mira.
@Component({
  selector: 'app-admin-conflictos',
  imports: [DatePipe, DecimalPipe],
  templateUrl: './conflictos.html',
  styleUrls: ['../ventas/ventas.scss', '../sin-conexion/sin-conexion.scss', './conflictos.scss'],
})
export class AdminConflictos implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(Auth);
  private readonly api = `${environment.apiUrl}/offline`;

  protected readonly estadoLabel = ESTADO_OPERACION;
  protected readonly tipoUsuario = TIPO_USUARIO;
  protected readonly esPlataforma = this.auth.currentUser()?.tipo === 'superadministrador';
  protected readonly puedeResolver = !this.esPlataforma && (this.auth.isAdmin() || this.auth.hasPermiso('2P-CU14'));

  protected readonly operaciones = signal<OperacionServidor[]>([]);
  protected readonly filtro = signal<string>(inject(ActivatedRoute).snapshot.data['estado'] ?? 'conflicto');
  protected readonly cargando = signal(true);
  protected readonly error = signal('');

  protected readonly resolviendo = signal<OperacionServidor | null>(null);
  protected readonly disponibles = signal<Disponible[]>([]);
  protected readonly lineas = signal<LineaAjuste[]>([]);
  protected readonly accion = signal<'ajustar' | 'anular'>('ajustar');
  protected readonly motivo = signal('');
  protected readonly errorModal = signal('');
  protected readonly guardando = signal(false);

  protected readonly totalAjuste = computed(() =>
    this.lineas().reduce((t, l) => t + (l.variante ? Number(l.item.precio) * l.cantidad : 0), 0),
  );

  ngOnInit(): void {
    void this.cargar();
  }

  protected async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = this.filtro() ? { estado: this.filtro() } : {};
      this.operaciones.set(await firstValueFrom(this.http.get<OperacionServidor[]>(`${this.api}/operaciones`, { params })));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar las operaciones sincronizadas.'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected filtrar(valor: string): void {
    this.filtro.set(valor);
    void this.cargar();
  }

  protected variantesDe(productoId: number): Disponible[] {
    return this.disponibles().filter((d) => d.producto_id === productoId);
  }

  protected clave(d: { talla_id: number; color_id: number }): string {
    return `${d.talla_id}-${d.color_id}`;
  }

  protected stockDe(l: LineaAjuste): number {
    return this.variantesDe(l.item.producto_id).find((d) => this.clave(d) === l.variante)?.stock ?? 0;
  }

  protected async abrir(o: OperacionServidor): Promise<void> {
    this.errorModal.set('');
    this.accion.set('ajustar');
    this.motivo.set('');
    try {
      const r = await firstValueFrom(
        this.http.get<{ operacion: OperacionServidor; disponibles: Disponible[] }>(`${this.api}/operaciones/${o.id}/opciones`),
      );
      this.disponibles.set(r.disponibles);
      // Por defecto: la misma variante con lo que haya (o quitarla si no hay).
      this.lineas.set(
        r.operacion.items.map((item) => {
          const misma = r.disponibles.find(
            (d) => d.producto_id === item.producto_id && d.talla_id === item.talla_id && d.color_id === item.color_id,
          );
          return {
            item,
            variante: misma ? this.clave(misma) : '',
            cantidad: misma ? Math.min(item.cantidad, misma.stock) : item.cantidad,
          };
        }),
      );
      this.resolviendo.set(r.operacion);
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos abrir el conflicto.'));
    }
  }

  protected cambiarLinea(i: number, cambios: Partial<LineaAjuste>): void {
    this.lineas.update((ls) => ls.map((l, k) => (k === i ? { ...l, ...cambios } : l)));
  }

  protected cerrar(): void {
    if (!this.guardando()) this.resolviendo.set(null);
  }

  protected async confirmar(): Promise<void> {
    const o = this.resolviendo();
    if (!o) return;
    let cuerpo: object;
    if (this.accion() === 'anular') {
      if (this.motivo().trim().length < 3) {
        this.errorModal.set('Escribe el motivo de la anulación.');
        return;
      }
      cuerpo = { accion: 'anular', motivo: this.motivo().trim() };
    } else {
      const elegidas = this.lineas().filter((l) => l.variante);
      if (!elegidas.length) {
        this.errorModal.set('Deja al menos una prenda, o anula la operación.');
        return;
      }
      if (elegidas.some((l) => l.cantidad < 1 || l.cantidad > this.stockDe(l))) {
        this.errorModal.set('Alguna cantidad supera el stock disponible.');
        return;
      }
      const vistos = new Set<string>();
      for (const l of elegidas) {
        const k = `${l.item.producto_id}-${l.variante}`;
        if (vistos.has(k)) {
          this.errorModal.set('Elegiste dos veces la misma talla y color: junta las cantidades.');
          return;
        }
        vistos.add(k);
      }
      cuerpo = {
        accion: 'ajustar',
        motivo: this.motivo().trim() || null,
        items: elegidas.map((l) => {
          const [talla, color] = l.variante.split('-').map(Number);
          return { producto_id: l.item.producto_id, talla_id: talla, color_id: color, cantidad: l.cantidad, precio: l.item.precio };
        }),
      };
    }
    this.guardando.set(true);
    this.errorModal.set('');
    try {
      await firstValueFrom(this.http.post<OperacionServidor>(`${this.api}/operaciones/${o.id}/resolver`, cuerpo));
      this.resolviendo.set(null);
      await this.cargar();
    } catch (err) {
      this.errorModal.set(mensajeError(err, 'No se pudo resolver el conflicto.'));
    } finally {
      this.guardando.set(false);
    }
  }
}
