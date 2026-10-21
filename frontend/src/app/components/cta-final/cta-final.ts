import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

// Banda de cierre de la portada: invita a crear la boutique.
@Component({
  selector: 'app-cta-final',
  imports: [RouterLink],
  templateUrl: './cta-final.html',
  styleUrl: './cta-final.scss',
})
export class CtaFinal {}
