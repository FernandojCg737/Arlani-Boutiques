import { DatePipe, DecimalPipe } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';

interface MensajeChat {
  id: number;
  remitente: 'cliente' | 'bot';
  mensaje: string;
  fecha: string;
  // CU18: lo que entendió el modelo de la tienda (mensajes del cliente).
  intencion: string | null;
  confianza: number | null;
}

@Component({
  selector: 'app-admin-chatbot-detalle',
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './chatbot-detalle.html',
  styleUrl: './chatbot-detalle.scss',
})
export class AdminChatbotDetalle implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);

  protected readonly mensajes = signal<MensajeChat[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal('');

  ngOnInit(): void {
    const clienteId = this.route.snapshot.paramMap.get('clienteId');
    if (!clienteId) {
      this.error.set('Cliente no encontrado.');
      this.loading.set(false);
      return;
    }
    void this.cargar(clienteId);
  }

  private async cargar(clienteId: string): Promise<void> {
    try {
      const res = await firstValueFrom(
        this.http.get<MensajeChat[]>(`${environment.apiUrl}/chatbot/cliente/${clienteId}`),
      );
      this.mensajes.set(res);
    } catch (err) {
      if (err instanceof HttpErrorResponse && err.status === 404) {
        this.error.set('Este cliente no tiene conversaciones registradas.');
      } else {
        this.error.set('No se pudo cargar la conversacion.');
      }
    } finally {
      this.loading.set(false);
    }
  }
}
