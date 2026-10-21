import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CONTACTO_LEGAL, DocumentoLegal, PRIVACIDAD, TERMINOS } from '../../data/legal';

// Política de privacidad (/privacidad) y Términos y condiciones (/terminos):
// la misma página, el documento sale de la ruta (data: { documento }).
// Google pide la de privacidad para publicar el inicio de sesión con Google.
@Component({
  selector: 'app-legal',
  imports: [RouterLink],
  templateUrl: './legal.html',
  styleUrl: './legal.scss',
})
export class Legal {
  private readonly tipo = inject(ActivatedRoute).snapshot.data['documento'] as 'privacidad' | 'terminos';

  protected readonly doc: DocumentoLegal = this.tipo === 'terminos' ? TERMINOS : PRIVACIDAD;
  protected readonly otro =
    this.tipo === 'terminos'
      ? { texto: 'Política de privacidad', ruta: '/privacidad' }
      : { texto: 'Términos y condiciones', ruta: '/terminos' };
  protected readonly contacto = CONTACTO_LEGAL;
}
