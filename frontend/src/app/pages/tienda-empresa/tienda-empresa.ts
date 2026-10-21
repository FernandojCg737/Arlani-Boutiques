import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { SucursalPublica, TiendaPublica, TiendaPublicaApi } from '../../services/tienda-publica';

// Ficha publica de una tienda en /tienda-<subdominio> cuando todavia no tiene
// catalogo (o esta suspendida): su marca y sus sucursales. Si ya tiene
// catalogo, esa misma direccion muestra sus productos (ver app.routes.ts).
@Component({
  selector: 'app-tienda-empresa',
  imports: [RouterLink],
  templateUrl: './tienda-empresa.html',
  styleUrl: './tienda-empresa.scss',
})
export class TiendaEmpresa {
  private readonly api = inject(TiendaPublicaApi);
  private readonly subdominio = inject(ActivatedRoute).snapshot.paramMap.get('subdominio') ?? '';

  protected readonly tienda = signal<TiendaPublica | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noExiste = signal(false);
  protected readonly error = signal(false);

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const tienda = await this.api.obtener(this.subdominio);
      if (tienda) this.tienda.set(tienda);
      else this.noExiste.set(true);
    } catch {
      this.error.set(true);
    } finally {
      this.cargando.set(false);
    }
  }

  protected inicial(nombre: string): string {
    return nombre.trim()[0]?.toUpperCase() ?? '?';
  }

  protected mapa(s: SucursalPublica): string {
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.direccion}, ${s.ciudad}`)}`;
  }
}
