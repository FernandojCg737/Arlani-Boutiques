import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { mensajeError } from '../../../services/plataforma';

type TipoMetodo = 'paypal' | 'qr' | 'transferencia' | 'otro' | 'contra_entrega';

interface MetodoPago {
  id: number;
  tipo: TipoMetodo;
  nombre: string;
  instrucciones: string | null;
  activo: boolean;
  orden: number;
  paypal_client_id: string | null;
  paypal_modo: 'sandbox' | 'live' | null;
  paypal_email: string | null;
  paypal_secret_mascara: string | null;
  qr_url: string | null;
  banco: string | null;
  numero_cuenta: string | null;
  tipo_cuenta: string | null;
  titular: string | null;
  documento_titular: string | null;
  requiere_comprobante: boolean;
}

interface Facturacion {
  razon_social: string | null;
  nit: string | null;
  direccion_fiscal: string | null;
  telefono: string | null;
  email_contacto: string | null;
}

interface FormMetodo {
  tipo: TipoMetodo;
  nombre: string;
  instrucciones: string;
  activo: boolean;
  paypal_client_id: string;
  paypal_secret: string;
  paypal_modo: 'sandbox' | 'live';
  paypal_email: string;
  banco: string;
  numero_cuenta: string;
  tipo_cuenta: string;
  titular: string;
  documento_titular: string;
}

const NOMBRE_POR_TIPO: Record<TipoMetodo, string> = {
  paypal: 'PayPal',
  qr: 'QR',
  transferencia: 'Transferencia bancaria',
  otro: 'Otro método',
  contra_entrega: 'Contra entrega',
};

// Gestionar metodos de pago: el Administrador de la tienda registra como le
// pagan sus clientes. PayPal (con SUS credenciales) se confirma solo; QR,
// transferencia y otros piden comprobante, que aprueba el personal en
// Gestion de Ventas. Tambien los datos que salen en sus facturas.
@Component({
  selector: 'app-admin-metodos-pago',
  imports: [],
  templateUrl: './metodos-pago.html',
  styleUrls: ['../sucursales/sucursales.scss', './metodos-pago.scss'],
})
export class AdminMetodosPago implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/metodos-pago`;

  protected readonly tipos: { tipo: TipoMetodo; titulo: string; detalle: string }[] = [
    { tipo: 'paypal', titulo: 'PayPal', detalle: 'Tarjeta o cuenta PayPal. El cobro se confirma solo y llega a tu cuenta.' },
    { tipo: 'qr', titulo: 'QR', detalle: 'El cliente escanea tu QR y sube su comprobante.' },
    { tipo: 'transferencia', titulo: 'Transferencia', detalle: 'Depósito a tu cuenta bancaria con comprobante.' },
    { tipo: 'otro', titulo: 'Otro', detalle: 'Tigo Money, efectivo al retirar… con comprobante.' },
    {
      tipo: 'contra_entrega',
      titulo: 'Contra entrega',
      detalle: 'Para compras hechas sin conexión: el cliente paga en efectivo al recibir o recoger.',
    },
  ];

  protected readonly metodos = signal<MetodoPago[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly aviso = signal('');

  protected readonly showForm = signal(false);
  protected readonly editando = signal<MetodoPago | null>(null);
  protected readonly f = signal<FormMetodo>(this.vacio('qr'));
  protected readonly qrNuevo = signal<string | null>(null);
  protected readonly errorForm = signal('');
  protected readonly saving = signal(false);

  protected readonly fact = signal<Facturacion>({
    razon_social: null,
    nit: null,
    direccion_fiscal: null,
    telefono: null,
    email_contacto: null,
  });
  protected readonly guardandoFact = signal(false);
  protected readonly avisoFact = signal('');
  protected readonly errorFact = signal('');

  ngOnInit(): void {
    void this.load();
    void this.cargarFacturacion();
  }

  private vacio(tipo: TipoMetodo): FormMetodo {
    return {
      tipo,
      nombre: NOMBRE_POR_TIPO[tipo],
      instrucciones: '',
      activo: true,
      paypal_client_id: '',
      paypal_secret: '',
      paypal_modo: 'sandbox',
      paypal_email: '',
      banco: '',
      numero_cuenta: '',
      tipo_cuenta: '',
      titular: '',
      documento_titular: '',
    };
  }

  protected tienePaypal(): boolean {
    return this.metodos().some((m) => m.tipo === 'paypal');
  }

  protected tituloTipo(tipo: TipoMetodo): string {
    return this.tipos.find((t) => t.tipo === tipo)?.titulo ?? tipo;
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.metodos.set(await firstValueFrom(this.http.get<MetodoPago[]>(this.base)));
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cargar tus métodos de pago.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected openNew(tipo: TipoMetodo): void {
    this.editando.set(null);
    this.f.set(this.vacio(tipo));
    this.qrNuevo.set(null);
    this.errorForm.set('');
    this.showForm.set(true);
  }

  protected edit(m: MetodoPago): void {
    this.editando.set(m);
    this.f.set({
      tipo: m.tipo,
      nombre: m.nombre,
      instrucciones: m.instrucciones ?? '',
      activo: m.activo,
      paypal_client_id: m.paypal_client_id ?? '',
      paypal_secret: '',
      paypal_modo: m.paypal_modo ?? 'sandbox',
      paypal_email: m.paypal_email ?? '',
      banco: m.banco ?? '',
      numero_cuenta: m.numero_cuenta ?? '',
      tipo_cuenta: m.tipo_cuenta ?? '',
      titular: m.titular ?? '',
      documento_titular: m.documento_titular ?? '',
    });
    this.qrNuevo.set(null);
    this.errorForm.set('');
    this.showForm.set(true);
  }

  protected closeForm(): void {
    this.showForm.set(false);
  }

  protected setF<K extends keyof FormMetodo>(campo: K, valor: FormMetodo[K]): void {
    this.f.update((f) => ({ ...f, [campo]: valor }));
  }

  protected alElegirQr(input: HTMLInputElement): void {
    const archivo = input.files?.[0];
    input.value = '';
    if (!archivo) return;
    if (archivo.size > 5 * 1024 * 1024) {
      this.errorForm.set('La imagen pesa más de 5 MB. Elige una más liviana.');
      return;
    }
    const lector = new FileReader();
    lector.onload = () => this.qrNuevo.set(String(lector.result));
    lector.readAsDataURL(archivo);
  }

  private payload(f: FormMetodo, m: MetodoPago | null, qr: string | null): Record<string, unknown> {
    return {
      tipo: f.tipo,
      nombre: f.nombre,
      instrucciones: f.instrucciones || null,
      activo: f.activo,
      orden: m?.orden ?? this.metodos().length,
      paypal_client_id: f.paypal_client_id || null,
      paypal_secret: f.paypal_secret || null,
      paypal_modo: f.tipo === 'paypal' ? f.paypal_modo : null,
      paypal_email: f.paypal_email || null,
      qr_imagen: qr,
      banco: f.banco || null,
      numero_cuenta: f.numero_cuenta || null,
      tipo_cuenta: f.tipo_cuenta || null,
      titular: f.titular || null,
      documento_titular: f.documento_titular || null,
    };
  }

  protected async submit(): Promise<void> {
    const f = this.f();
    const m = this.editando();
    if (f.nombre.trim().length < 2) {
      this.errorForm.set('Ponle un nombre al método (es lo que verá el cliente).');
      return;
    }
    if (f.tipo === 'paypal' && !f.paypal_email.includes('@')) {
      this.errorForm.set('Escribe el correo de tu cuenta PayPal: ahí te llega lo de las compras pagadas con PayPal.');
      return;
    }
    if (f.tipo === 'qr' && !this.qrNuevo() && !m?.qr_url) {
      this.errorForm.set('Sube la imagen de tu QR de cobro.');
      return;
    }
    this.saving.set(true);
    this.errorForm.set('');
    try {
      const cuerpo = this.payload(f, m, this.qrNuevo());
      if (m) await firstValueFrom(this.http.put(`${this.base}/${m.id}`, cuerpo));
      else await firstValueFrom(this.http.post(this.base, cuerpo));
      this.showForm.set(false);
      this.aviso.set(m ? 'Método actualizado.' : 'Método agregado: tus clientes ya lo ven al pagar.');
      await this.load();
    } catch (err) {
      this.errorForm.set(mensajeError(err, 'No pudimos guardar el método de pago.'));
    } finally {
      this.saving.set(false);
    }
  }

  protected async alternarActivo(m: MetodoPago): Promise<void> {
    this.error.set('');
    try {
      const f = { ...this.vacio(m.tipo), ...this.formDe(m), activo: !m.activo };
      await firstValueFrom(this.http.put(`${this.base}/${m.id}`, this.payload(f, m, null)));
      await this.load();
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos cambiar el estado del método.'));
    }
  }

  private formDe(m: MetodoPago): Partial<FormMetodo> {
    return {
      nombre: m.nombre,
      instrucciones: m.instrucciones ?? '',
      paypal_client_id: m.paypal_client_id ?? '',
      paypal_modo: m.paypal_modo ?? 'sandbox',
      paypal_email: m.paypal_email ?? '',
      banco: m.banco ?? '',
      numero_cuenta: m.numero_cuenta ?? '',
      tipo_cuenta: m.tipo_cuenta ?? '',
      titular: m.titular ?? '',
      documento_titular: m.documento_titular ?? '',
    };
  }

  protected async remove(m: MetodoPago): Promise<void> {
    if (!confirm(`¿Eliminar el método "${m.nombre}"? Tus clientes ya no podrán pagar con él.`)) return;
    try {
      await firstValueFrom(this.http.delete(`${this.base}/${m.id}`));
      await this.load();
    } catch (err) {
      this.error.set(mensajeError(err, 'No pudimos eliminar el método.'));
    }
  }

  // ------------------------------------------------ datos de facturacion
  private async cargarFacturacion(): Promise<void> {
    try {
      this.fact.set(await firstValueFrom(this.http.get<Facturacion>(`${environment.apiUrl}/mi-empresa/facturacion`)));
    } catch {
      // la seccion queda vacia; al guardar se informa el error
    }
  }

  protected setFact<K extends keyof Facturacion>(campo: K, valor: string): void {
    this.avisoFact.set('');
    this.fact.update((f) => ({ ...f, [campo]: valor }));
  }

  protected async guardarFacturacion(): Promise<void> {
    this.guardandoFact.set(true);
    this.errorFact.set('');
    try {
      this.fact.set(
        await firstValueFrom(this.http.put<Facturacion>(`${environment.apiUrl}/mi-empresa/facturacion`, this.fact())),
      );
      this.avisoFact.set('Listo: tus próximas facturas salen con estos datos.');
    } catch (err) {
      this.errorFact.set(mensajeError(err, 'No pudimos guardar tus datos de facturación.'));
    } finally {
      this.guardandoFact.set(false);
    }
  }
}
