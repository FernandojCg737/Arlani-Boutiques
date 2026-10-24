import { HttpClient } from '@angular/common/http';
import { Component, inject, input, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { descargarArchivo } from '../../pages/admin/reportes/reportes-export';
import { mensajeError } from '../../services/plataforma';
import { TablaReporte } from './tabla-reporte';

type Formato = 'pdf' | 'excel' | 'csv' | 'html';

const EXTENSION: Record<Formato, string> = { pdf: 'pdf', excel: 'xlsx', csv: 'csv', html: 'html' };
const NOMBRE: Record<Formato, string> = { pdf: 'PDF', excel: 'Excel', csv: 'CSV', html: 'HTML' };

// Exportar un reporte (CU07 y CU20): Imprimir, PDF, Excel, CSV y HTML, o
// enviarlo por correo en cualquiera de esos formatos (el correo se pide aquí).
// Dos modos: con [tabla] (cualquier reporte ya armado: estático o dinámico)
// o con [url] + [params] (los reportes del CU07 que se exportan en el servidor).
@Component({
  selector: 'app-exportar-reporte',
  template: `
    <div class="exportar">
      <button type="button" (click)="imprimir()">Imprimir</button>
      @for (f of formatos; track f) {
        <button type="button" [disabled]="ocupado()" (click)="descargar(f)">{{ nombre[f] }}</button>
      }
      <button type="button" class="exportar__correo" [disabled]="ocupado()" (click)="abrirCorreo()">Enviar por correo</button>
    </div>
    @if (aviso()) {
      <p class="exportar__aviso" [class.is-error]="esError()">{{ aviso() }}</p>
    }

    @if (correoAbierto()) {
      <div class="exportar-fondo" (click)="correoAbierto.set(false)">
        <div class="exportar-modal" (click)="$event.stopPropagation()" role="dialog" aria-modal="true" aria-labelledby="exportar-titulo">
          <h2 id="exportar-titulo">Enviar reporte por correo</h2>
          <p>El reporte llega como archivo adjunto en el formato que elijas.</p>
          <label>
            <span>Correo de destino</span>
            <input type="email" placeholder="nombre@correo.com" [value]="correo()" (input)="correo.set($any($event.target).value)" />
          </label>
          <span class="exportar-modal__etiqueta">Formato</span>
          <div class="exportar-modal__formatos">
            @for (f of formatos; track f) {
              <button type="button" [class.is-activo]="formatoCorreo() === f" (click)="formatoCorreo.set(f)">{{ nombre[f] }}</button>
            }
          </div>
          @if (errorCorreo()) {
            <p class="exportar__aviso is-error">{{ errorCorreo() }}</p>
          }
          <div class="exportar-modal__acciones">
            <button type="button" class="is-secundario" (click)="correoAbierto.set(false)">Cancelar</button>
            <button type="button" [disabled]="ocupado()" (click)="enviar()">{{ ocupado() ? 'Enviando…' : 'Enviar' }}</button>
          </div>
        </div>
      </div>
    }
  `,
  styles: `
    .exportar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    button {
      border: 1px solid #ddd;
      background: #fff;
      color: #1f2a44;
      padding: 7px 12px;
      font: inherit;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .exportar__correo {
      background: #1f2a44;
      border-color: #1f2a44;
      color: #fff;
    }
    .exportar__aviso {
      margin: 6px 0 0;
      font-size: 12px;
      color: #2e7d32;
    }
    .exportar__aviso.is-error {
      color: #b3261e;
    }
    .exportar-fondo {
      position: fixed;
      inset: 0;
      z-index: 1500;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      background: rgba(0, 0, 0, 0.55);
    }
    .exportar-modal {
      width: 100%;
      max-width: 420px;
      padding: 24px;
      background: #fff;
    }
    .exportar-modal h2 {
      margin: 0 0 4px;
      font-size: 17px;
      text-transform: uppercase;
      color: #1f2a44;
    }
    .exportar-modal p {
      margin: 0 0 14px;
      font-size: 13px;
      color: #666;
    }
    .exportar-modal label span,
    .exportar-modal__etiqueta {
      display: block;
      margin-bottom: 6px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: #777;
    }
    .exportar-modal input {
      width: 100%;
      box-sizing: border-box;
      margin-bottom: 14px;
      padding: 10px 12px;
      border: 1px solid #ddd;
      font: inherit;
    }
    .exportar-modal__formatos {
      display: flex;
      gap: 6px;
      margin-bottom: 16px;
    }
    .exportar-modal__formatos button {
      flex: 1;
    }
    .exportar-modal__formatos .is-activo {
      background: #1f2a44;
      border-color: #1f2a44;
      color: #fff;
    }
    .exportar-modal__acciones {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }
    .exportar-modal__acciones button:last-child {
      background: #1f2a44;
      border-color: #1f2a44;
      color: #fff;
    }
    @media print {
      :host {
        display: none;
      }
    }
  `,
})
export class ExportarReporte {
  private readonly http = inject(HttpClient);

  readonly tabla = input<TablaReporte | null>(null);
  readonly url = input<string | null>(null);
  readonly params = input<Record<string, string>>({});
  readonly nombreArchivo = input('reporte');

  protected readonly formatos: Formato[] = ['pdf', 'excel', 'csv', 'html'];
  protected readonly nombre = NOMBRE;
  protected readonly ocupado = signal(false);
  protected readonly aviso = signal('');
  protected readonly esError = signal(false);
  protected readonly correoAbierto = signal(false);
  protected readonly correo = signal('');
  protected readonly formatoCorreo = signal<Formato>('pdf');
  protected readonly errorCorreo = signal('');

  protected imprimir(): void {
    window.print();
  }

  private archivo(formato: Formato) {
    const tabla = this.tabla();
    if (tabla) {
      return this.http.post(`${environment.apiUrl}/reportes/exportar-tabla`, { tabla, formato }, { responseType: 'blob' });
    }
    return this.http.get(this.url()!, { params: { ...this.params(), formato }, responseType: 'blob' });
  }

  private porCorreo(formato: Formato, correo: string) {
    const tabla = this.tabla();
    if (tabla) {
      return this.http.post<{ enviado: boolean }>(`${environment.apiUrl}/reportes/exportar-tabla`, { tabla, formato, correo });
    }
    return this.http.get<{ enviado: boolean }>(this.url()!, { params: { ...this.params(), formato, correo } });
  }

  protected async descargar(formato: Formato): Promise<void> {
    this.ocupado.set(true);
    this.aviso.set('');
    try {
      const blob = await firstValueFrom(this.archivo(formato));
      descargarArchivo(blob, `${this.tabla()?.titulo ? this.slug(this.tabla()!.titulo) : this.nombreArchivo()}.${EXTENSION[formato]}`);
    } catch (err) {
      this.esError.set(true);
      this.aviso.set(mensajeError(err, 'No se pudo exportar el reporte.'));
    } finally {
      this.ocupado.set(false);
    }
  }

  protected abrirCorreo(): void {
    this.errorCorreo.set('');
    this.correoAbierto.set(true);
  }

  protected async enviar(): Promise<void> {
    const correo = this.correo().trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) {
      this.errorCorreo.set('Escribe un correo válido.');
      return;
    }
    this.ocupado.set(true);
    this.errorCorreo.set('');
    try {
      await firstValueFrom(this.porCorreo(this.formatoCorreo(), correo));
      this.correoAbierto.set(false);
      this.esError.set(false);
      this.aviso.set(`Reporte enviado a ${correo} en ${NOMBRE[this.formatoCorreo()]}.`);
    } catch (err) {
      this.errorCorreo.set(mensajeError(err, 'No se pudo enviar el correo.'));
    } finally {
      this.ocupado.set(false);
    }
  }

  private slug(texto: string): string {
    return texto
      .toLowerCase()
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '');
  }
}
