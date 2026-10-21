import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import {
  MAX_SUCURSALES,
  PLANES,
  Periodo,
  Plan,
  esPrueba,
  planParaSucursales,
  precioAnual,
  precioPorMes,
} from '../../data/planes';
import { Auth } from '../../services/auth';
import { enlaceDisponible, enlaceTiendaCorto, rutaTienda } from '../../services/plataforma';
import { RegistroEmpresaApi } from '../../services/registro-empresa';

type Paso = 0 | 1 | 2;
const ULTIMO_PASO: Paso = 2;

const CIUDADES = ['Santa Cruz', 'La Paz', 'Cochabamba', 'Sucre', 'Tarija', 'Oruro', 'Potosí', 'Trinidad', 'Cobija'];

// Colores de marca para elegir; se ven al instante en la vista previa.
const COLORES = [
  { nombre: 'Azul noche', valor: '#1f2a44' },
  { nombre: 'Coral', valor: '#c4503d' },
  { nombre: 'Verde botella', valor: '#203c40' },
  { nombre: 'Vino', valor: '#6d2338' },
  { nombre: 'Negro', valor: '#141414' },
  { nombre: 'Arena', valor: '#a07d5a' },
];


// "Mi Boutique Ñandú" -> "mi-boutique-nandu"
function aSubdominio(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 30);
}

// Alta de una boutique nueva en Arlani, en tres pasos. Solo con sesión
// iniciada (authGuard): el usuario logueado queda como administrador. A la izquierda una
// vista previa de la tienda se arma en vivo con lo que se va cargando.
@Component({
  selector: 'app-registro-empresa',
  imports: [RouterLink],
  templateUrl: './registro-empresa.html',
  styleUrl: './registro-empresa.scss',
})
export class RegistroEmpresa {
  private readonly api = inject(RegistroEmpresaApi);
  // "arlani.onrender.com/tienda-": el enlace va por ruta, sin dominio propio.
  protected readonly prefijoEnlace = enlaceTiendaCorto();
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(Auth);

  protected readonly planes = PLANES;
  protected readonly maxSucursales = MAX_SUCURSALES;
  protected readonly esPrueba = esPrueba;
  protected readonly ciudades = CIUDADES;
  protected readonly colores = COLORES;
  protected readonly titulosPasos = ['Plan', 'Tu boutique', 'Confirmar'];

  protected readonly paso = signal<Paso>(0);
  // Se marca al intentar avanzar: recién ahí se muestran los errores.
  protected readonly intentoAvanzar = signal(false);
  protected readonly enviando = signal(false);
  protected readonly errorEnvio = signal('');
  protected readonly creada = signal(false);

  // Paso 1: plan
  protected readonly planId = signal(this.leerPlanInicial());
  protected readonly periodo = signal<Periodo>(
    this.route.snapshot.queryParamMap.get('periodo') === 'anual' ? 'anual' : 'mensual',
  );

  // Paso 2: boutique
  protected readonly nombreBoutique = signal('');
  protected readonly subdominio = signal('');
  // Mientras el usuario no edite la dirección a mano, sigue al nombre.
  private subdominioEditado = false;
  protected readonly ciudad = signal('Santa Cruz');
  protected readonly sucursales = signal(1);
  protected readonly color = signal(COLORES[0].valor);

  protected readonly plan = computed<Plan>(() => PLANES.find((p) => p.id === this.planId()) ?? PLANES[0]);
  protected readonly precioMes = computed(() => precioPorMes(this.plan(), this.periodo()));
  protected readonly precioAnio = computed(() => precioAnual(this.plan()));

  // Si las sucursales no entran en el plan elegido, se sugiere el que alcanza.
  protected readonly planSugerido = computed<Plan | null>(() => {
    const max = this.plan().maxSucursales;
    if (this.sucursales() <= max || this.sucursales() > MAX_SUCURSALES) return null;
    return planParaSucursales(this.sucursales());
  });

  // Enlace final: si el escrito ya lo usa otra tienda, con un numero al final.
  protected readonly enlaceFinal = enlaceDisponible(() => this.subdominio());
  protected readonly enlaceOcupado = computed(
    () => this.subdominio().length >= 3 && this.enlaceFinal() !== this.subdominio(),
  );
  protected readonly subdominioVista = computed(() => this.enlaceFinal() || 'tuboutique');
  // Con el que quedo creada (lo confirma el backend).
  protected readonly subdominioCreado = signal('');
  protected readonly rutaTienda = rutaTienda;

  protected readonly errores = computed(() => {
    const e: Record<string, string> = {};
    const nombre = this.nombreBoutique().trim();
    if (nombre.length < 2) e['nombreBoutique'] = 'Escribí el nombre de tu boutique.';
    if (!/^[a-z0-9](?:[a-z0-9-]{1,28}[a-z0-9])$/.test(this.subdominio()))
      e['subdominio'] = 'Entre 3 y 30 letras, números o guiones (sin espacios ni acentos).';
    if (!Number.isInteger(this.sucursales()) || this.sucursales() < 1 || this.sucursales() > MAX_SUCURSALES)
      e['sucursales'] = `Entre 1 y ${MAX_SUCURSALES} sucursales (máximo del plan Profesional).`;
    return e;
  });

  private readonly camposPorPaso: Record<Paso, string[]> = {
    0: [],
    1: ['nombreBoutique', 'subdominio', 'sucursales'],
    2: [],
  };

  protected precioDe(plan: Plan): number {
    return precioPorMes(plan, this.periodo());
  }

  protected error(campo: string): string | null {
    if (!this.intentoAvanzar()) return null;
    return this.errores()[campo] ?? null;
  }

  protected siguiente(): void {
    const invalido = this.camposPorPaso[this.paso()].some((c) => this.errores()[c]);
    if (invalido) {
      this.intentoAvanzar.set(true);
      return;
    }
    this.intentoAvanzar.set(false);
    if (this.paso() < ULTIMO_PASO) this.paso.update((p) => (p + 1) as Paso);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  protected anterior(): void {
    this.intentoAvanzar.set(false);
    if (this.paso() > 0) this.paso.update((p) => (p - 1) as Paso);
  }

  // Solo se puede saltar a pasos ya visitados (hacia atrás).
  protected irAPaso(destino: number): void {
    if (destino < this.paso()) {
      this.intentoAvanzar.set(false);
      this.paso.set(destino as Paso);
    }
  }

  protected alCambiarNombre(valor: string): void {
    this.nombreBoutique.set(valor);
    if (!this.subdominioEditado) this.subdominio.set(aSubdominio(valor));
  }

  protected alCambiarSubdominio(valor: string): void {
    this.subdominioEditado = true;
    this.subdominio.set(aSubdominio(valor));
  }

  protected alCambiarSucursales(valor: string): void {
    this.sucursales.set(Math.floor(Number(valor)) || 0);
  }

  protected async crear(): Promise<void> {
    this.enviando.set(true);
    this.errorEnvio.set('');
    try {
      const creada = await this.api.registrar({
        plan: this.planId(),
        periodo: this.periodo(),
        boutique: {
          nombre: this.nombreBoutique().trim(),
          subdominio: this.subdominio(),
          ciudad: this.ciudad(),
          sucursales: this.sucursales(),
          color: this.color(),
        },
      });
      this.subdominioCreado.set(creada.subdominio);
      this.creada.set(true);
    } catch (err) {
      // Solo los rechazos de validación (p. ej. "esa dirección ya está en
      // uso") traen un mensaje pensado para el usuario; el resto (servidor
      // caído, 404, 500) se muestra con un mensaje genérico.
      const esRechazo = err instanceof HttpErrorResponse && [400, 409, 422].includes(err.status);
      const detalle = esRechazo ? err.error?.detail : null;
      this.errorEnvio.set(
        typeof detalle === 'string' ? detalle : 'No pudimos crear tu boutique en este momento. Probá de nuevo en unos minutos.',
      );
    } finally {
      this.enviando.set(false);
    }
  }

  private leerPlanInicial(): string {
    const pedido = this.route.snapshot.queryParamMap.get('plan');
    return PLANES.some((p) => p.id === pedido) ? pedido! : 'basico';
  }
}
