import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, input, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { MapaUbicacion } from '../../../components/mapa-ubicacion/mapa-ubicacion';
import { Mapa, Punto, enlaceMapa } from '../../../services/mapa';

export interface DireccionCliente {
  id: number;
  alias: string;
  direccion: string;
  referencia: string | null;
  ciudad: string | null;
  latitud: string;
  longitud: string;
  predeterminada: boolean;
}

interface FormDireccion {
  alias: string;
  direccion: string;
  referencia: string;
  ciudad: string;
  punto: Punto | null;
  predeterminada: boolean;
}

// Mis direcciones: el cliente guarda a donde quiere que le envien sus
// compras, con la ubicacion en el mapa (su GPS o moviendo el pin). Al pagar
// elige una si quiere envio a domicilio. En el checkout se usa solo el
// formulario (soloFormulario) para agregar una sin salir del pago.
@Component({
  selector: 'app-mis-direcciones',
  imports: [MapaUbicacion],
  templateUrl: './mis-direcciones.html',
  styleUrls: ['../perfil.scss', './mis-direcciones.scss'],
})
export class MisDirecciones implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly mapa = inject(Mapa);
  private readonly api = `${environment.apiUrl}/direcciones`;

  readonly soloFormulario = input(false);
  readonly guardada = output<DireccionCliente>();

  protected readonly direcciones = signal<DireccionCliente[]>([]);
  protected readonly cargando = signal(true);
  protected readonly aviso = signal('');

  protected readonly abierto = signal(false);
  protected readonly editando = signal<DireccionCliente | null>(null);
  protected readonly f = signal<FormDireccion>(this.vacio());
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  // El texto lo sugiere el mapa hasta que el cliente lo escribe a mano.
  private textoManual = false;

  protected readonly aliasRapidos = ['Casa', 'Trabajo', 'Casa de mis papás'];
  protected readonly enlaceMapa = enlaceMapa;

  ngOnInit(): void {
    if (!this.soloFormulario()) void this.cargar();
  }

  private vacio(): FormDireccion {
    return { alias: 'Casa', direccion: '', referencia: '', ciudad: '', punto: null, predeterminada: false };
  }

  private async cargar(): Promise<void> {
    try {
      this.direcciones.set(await firstValueFrom(this.http.get<DireccionCliente[]>(this.api)));
    } catch {
      this.direcciones.set([]);
    } finally {
      this.cargando.set(false);
    }
  }

  abrirNueva(): void {
    this.editando.set(null);
    this.f.set(this.vacio());
    this.textoManual = false;
    this.error.set('');
    this.abierto.set(true);
  }

  protected editar(d: DireccionCliente): void {
    this.editando.set(d);
    this.f.set({
      alias: d.alias,
      direccion: d.direccion,
      referencia: d.referencia ?? '',
      ciudad: d.ciudad ?? '',
      punto: { lat: Number(d.latitud), lng: Number(d.longitud) },
      predeterminada: d.predeterminada,
    });
    this.textoManual = true;
    this.error.set('');
    this.abierto.set(true);
  }

  protected cerrar(): void {
    this.abierto.set(false);
  }

  protected setF<K extends keyof FormDireccion>(campo: K, valor: FormDireccion[K]): void {
    if (campo === 'direccion') this.textoManual = true;
    this.f.update((f) => ({ ...f, [campo]: valor }));
  }

  protected async alMoverPin(p: Punto): Promise<void> {
    this.f.update((f) => ({ ...f, punto: p }));
    if (this.textoManual) return;
    const sugerida = await this.mapa.direccionDe(p);
    if (sugerida && !this.textoManual) {
      this.f.update((f) => ({ ...f, direccion: sugerida.direccion, ciudad: sugerida.ciudad ?? f.ciudad }));
    }
  }

  protected async guardar(): Promise<void> {
    const f = this.f();
    if (!f.punto) {
      this.error.set('Marca tu ubicación en el mapa (usa tu GPS o mueve el pin).');
      return;
    }
    if (f.alias.trim().length < 2 || f.direccion.trim().length < 5) {
      this.error.set('Ponle un nombre y escribe la dirección (calle y número o zona).');
      return;
    }
    this.guardando.set(true);
    this.error.set('');
    const cuerpo = {
      alias: f.alias.trim(),
      direccion: f.direccion.trim(),
      referencia: f.referencia.trim() || null,
      ciudad: f.ciudad.trim() || null,
      latitud: f.punto.lat.toFixed(6),
      longitud: f.punto.lng.toFixed(6),
      predeterminada: f.predeterminada,
    };
    try {
      const e = this.editando();
      const d = e
        ? await firstValueFrom(this.http.put<DireccionCliente>(`${this.api}/${e.id}`, cuerpo))
        : await firstValueFrom(this.http.post<DireccionCliente>(this.api, cuerpo));
      this.abierto.set(false);
      this.guardada.emit(d);
      if (!this.soloFormulario()) {
        this.aviso.set(e ? 'Dirección actualizada.' : 'Dirección guardada: ya puedes elegirla al pagar.');
        await this.cargar();
      }
    } catch (err) {
      this.error.set(this.extraerError(err));
    } finally {
      this.guardando.set(false);
    }
  }

  protected async borrar(d: DireccionCliente): Promise<void> {
    if (!confirm(`¿Borrar la dirección "${d.alias}"? Tus compras ya hechas no cambian.`)) return;
    try {
      await firstValueFrom(this.http.delete(`${this.api}/${d.id}`));
      await this.cargar();
    } catch (err) {
      this.aviso.set(this.extraerError(err));
    }
  }

  protected async predeterminar(d: DireccionCliente): Promise<void> {
    try {
      await firstValueFrom(
        this.http.put(`${this.api}/${d.id}`, {
          alias: d.alias,
          direccion: d.direccion,
          referencia: d.referencia,
          ciudad: d.ciudad,
          latitud: d.latitud,
          longitud: d.longitud,
          predeterminada: true,
        }),
      );
      await this.cargar();
    } catch (err) {
      this.aviso.set(this.extraerError(err));
    }
  }

  private extraerError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) return 'Revisa los datos de la dirección.';
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'No se pudo guardar la dirección.';
  }
}
