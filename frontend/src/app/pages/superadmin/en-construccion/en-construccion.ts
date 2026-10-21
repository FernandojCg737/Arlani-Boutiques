import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { map } from 'rxjs/operators';
import { buscarCaso } from '../superadmin-menu';

// CU del 2do parcial que todavía no tiene pantalla: muestra qué va a hacer
// mientras se construye.
@Component({
  selector: 'app-superadmin-en-construccion',
  templateUrl: './en-construccion.html',
  styleUrl: './en-construccion.scss',
})
export class SuperadminEnConstruccion {
  private readonly route = inject(ActivatedRoute);
  private readonly codigo = toSignal(this.route.paramMap.pipe(map((p) => p.get('codigo') ?? '')), {
    initialValue: '',
  });
  protected readonly ubicacion = computed(() => buscarCaso('p2', this.codigo()));
}
