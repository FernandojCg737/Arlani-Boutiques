import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Auth } from '../../../services/auth';
import { ADMIN_MENU } from '../admin-menu';

interface AccesoRapido {
  code: string;
  label: string;
  route: string;
}

@Component({
  selector: 'app-admin-home',
  imports: [RouterLink],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class AdminHome {
  protected readonly auth = inject(Auth);

  protected readonly accesosRapidos = computed<AccesoRapido[]>(() => {
    const esAdmin = this.auth.isAdmin();
    const items: AccesoRapido[] = [];
    for (const pkg of ADMIN_MENU) {
      for (const uc of pkg.useCases) {
        if (uc.route && (esAdmin || uc.code === 'CU15' || this.auth.hasPermiso(uc.permiso ?? uc.code))) {
          items.push({ code: uc.code, label: uc.label, route: uc.route });
        }
      }
    }
    return items;
  });
}
