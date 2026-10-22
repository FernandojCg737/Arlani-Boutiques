import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';

interface Imagen {
  id: number;
  url: string;
  orden: number;
}

interface PrendaAr {
  url: string;
  ancla_hombro_izq_x: string;
  ancla_hombro_izq_y: string;
  ancla_hombro_der_x: string;
  ancla_hombro_der_y: string;
  ancla_torso_y: string;
}

interface Disponibilidad {
  sucursal_nombre: string;
  cantidad: number;
}

interface Inventario {
  id: number;
  sucursal_id: number;
  sucursal_nombre: string;
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  cantidad: number;
}

interface Producto {
  id: number;
  nombre: string;
  descripcion: string | null;
  precio: string;
  precio_original: string | null;
  estado: string;
  categoria_id: number;
  categoria_nombre: string;
  marca_id: number;
  marca_nombre: string;
  proveedor_id: number;
  proveedor_nombre: string;
  temporada_id: number;
  temporada_nombre: string;
  coleccion_id: number;
  coleccion_nombre: string;
  imagenes: Imagen[];
  sucursales_disponibles: Disponibilidad[];
  prenda_ar: PrendaAr | null;
}

interface Opcion {
  id: number;
  nombre: string;
}

interface CatalogoBase {
  categorias: Opcion[];
  marcas: Opcion[];
  temporadas: Opcion[];
  colecciones: Opcion[];
  proveedores: Opcion[];
  sucursales: Opcion[];
  tallas: Opcion[];
  colores: Opcion[];
}

const MARCA_OTRO = -1;
const COLOR_OTRO = -1;

@Component({
  selector: 'app-admin-productos',
  imports: [RouterLink],
  templateUrl: './productos.html',
  styleUrl: './productos.scss',
})
export class AdminProductos implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly productos = signal<Producto[]>([]);
  protected readonly catalogo = signal<CatalogoBase>({
    categorias: [],
    marcas: [],
    temporadas: [],
    colecciones: [],
    proveedores: [],
    sucursales: [],
    tallas: [],
    colores: [],
  });
  protected readonly marcaOtro = MARCA_OTRO;
  protected readonly colorOtro = COLOR_OTRO;
  protected readonly buscar = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  protected readonly showForm = signal(false);
  protected readonly editingProducto = signal<Producto | null>(null);
  protected readonly fNombre = signal('');
  protected readonly fDescripcion = signal('');
  protected readonly fPrecio = signal('');
  protected readonly fPrecioOriginal = signal('');
  protected readonly fCategoriaId = signal<number | null>(null);
  protected readonly fMarcaId = signal<number | null>(null);
  protected readonly fMarcaNueva = signal('');
  protected readonly fProveedorId = signal<number | null>(null);
  protected readonly fTemporadaId = signal<number | null>(null);
  protected readonly fColeccionId = signal<number | null>(null);
  protected readonly fEstado = signal('activo');
  protected readonly saving = signal(false);
  protected readonly uploadingImagen = signal(false);
  protected readonly uploadingArImagen = signal(false);
  protected readonly formError = signal('');

  protected readonly inventario = signal<Inventario[]>([]);
  protected readonly loadingInventario = signal(false);
  protected readonly nStockSucursalId = signal<number | null>(null);
  protected readonly nStockTallaId = signal<number | null>(null);
  protected readonly nStockColorId = signal<number | null>(null);
  protected readonly nStockColorNuevo = signal('');
  protected readonly nStockCantidad = signal('');
  protected readonly savingStock = signal(false);
  protected readonly stockError = signal('');

  ngOnInit(): void {
    this.loadCommon();
  }

  protected search(): void {
    this.loadProductos();
  }

  protected openCreate(): void {
    this.editingProducto.set(null);
    this.fNombre.set('');
    this.fDescripcion.set('');
    this.fPrecio.set('');
    this.fPrecioOriginal.set('');
    this.fCategoriaId.set(this.catalogo().categorias[0]?.id ?? null);
    // Sin marcas todavia (tienda nueva): "Otro..." elegido, con el campo para escribirla.
    this.fMarcaId.set(this.catalogo().marcas[0]?.id ?? MARCA_OTRO);
    this.fMarcaNueva.set('');
    this.fProveedorId.set(this.catalogo().proveedores[0]?.id ?? null);
    this.fTemporadaId.set(this.catalogo().temporadas[0]?.id ?? null);
    this.fColeccionId.set(this.catalogo().colecciones[0]?.id ?? null);
    this.fEstado.set('activo');
    this.formError.set('');
    this.showForm.set(true);
  }

  protected openEdit(p: Producto): void {
    this.editingProducto.set(p);
    this.fNombre.set(p.nombre);
    this.fDescripcion.set(p.descripcion ?? '');
    this.fPrecio.set(p.precio);
    this.fPrecioOriginal.set(p.precio_original ?? '');
    this.fCategoriaId.set(p.categoria_id);
    this.fMarcaId.set(p.marca_id);
    this.fMarcaNueva.set('');
    this.fProveedorId.set(p.proveedor_id);
    this.fTemporadaId.set(p.temporada_id);
    this.fColeccionId.set(p.coleccion_id);
    this.fEstado.set(p.estado);
    this.formError.set('');
    this.showForm.set(true);
    this.resetNuevoStockForm();
    this.loadInventario(p.id);
  }

  protected closeForm(): void {
    this.showForm.set(false);
    this.editingProducto.set(null);
  }

  protected async submitForm(): Promise<void> {
    // Se dice exactamente que falta (una tienda nueva no tiene proveedores,
    // temporadas ni colecciones hasta que los registra).
    const faltan = [
      !this.fNombre() && 'el nombre',
      !this.fPrecio() && 'el precio',
      !this.fCategoriaId() && 'la categoría',
      (!this.fMarcaId() || (this.fMarcaId() === this.marcaOtro && !this.fMarcaNueva().trim())) &&
        'el nombre de la marca',
      !this.fProveedorId() && 'un proveedor',
      !this.fTemporadaId() && 'una temporada',
      !this.fColeccionId() && 'una colección',
    ].filter((f): f is string => !!f);
    if (faltan.length) {
      this.formError.set(`Falta ${faltan.join(', ')}.`);
      return;
    }

    this.formError.set('');
    this.saving.set(true);
    try {
      let marcaId = this.fMarcaId();
      if (marcaId === this.marcaOtro) {
        const marca = await firstValueFrom(
          this.http.post<Opcion>(`${environment.apiUrl}/productos/marcas`, { nombre: this.fMarcaNueva().trim() }),
        );
        this.catalogo.update((c) => ({ ...c, marcas: [...c.marcas, marca].sort((a, b) => a.nombre.localeCompare(b.nombre)) }));
        marcaId = marca.id;
      }

      const payload = {
        nombre: this.fNombre(),
        descripcion: this.fDescripcion() || null,
        precio: this.fPrecio(),
        precio_original: this.fPrecioOriginal() || null,
        categoria_id: this.fCategoriaId(),
        marca_id: marcaId,
        proveedor_id: this.fProveedorId(),
        temporada_id: this.fTemporadaId(),
        coleccion_id: this.fColeccionId(),
      };

      const editing = this.editingProducto();
      let resultado: Producto;
      if (editing) {
        resultado = await firstValueFrom(
          this.http.put<Producto>(`${environment.apiUrl}/productos/${editing.id}`, { ...payload, estado: this.fEstado() }),
        );
      } else {
        resultado = await firstValueFrom(this.http.post<Producto>(`${environment.apiUrl}/productos`, payload));
      }

      this.productos.update((lista) => {
        const idx = lista.findIndex((x) => x.id === resultado.id);
        if (idx === -1) return [...lista, resultado];
        const copia = [...lista];
        copia[idx] = resultado;
        return copia;
      });

      this.showForm.set(false);
      this.editingProducto.set(null);
      await this.loadProductos();
    } catch (err) {
      this.formError.set(this.extractError(err));
    } finally {
      this.saving.set(false);
    }
  }

  protected async toggleEstado(p: Producto): Promise<void> {
    const nuevoEstado = p.estado === 'activo' ? 'inactivo' : 'activo';
    const accion = nuevoEstado === 'inactivo' ? 'desactivar' : 'activar';
    if (!confirm(`Seguro que queres ${accion} "${p.nombre}"?`)) return;

    try {
      await firstValueFrom(
        this.http.put(`${environment.apiUrl}/productos/${p.id}`, {
          nombre: p.nombre,
          descripcion: p.descripcion,
          precio: p.precio,
          precio_original: p.precio_original,
          categoria_id: p.categoria_id,
          marca_id: p.marca_id,
          proveedor_id: p.proveedor_id,
          temporada_id: p.temporada_id,
          coleccion_id: p.coleccion_id,
          estado: nuevoEstado,
        }),
      );
      await this.loadProductos();
    } catch (err) {
      this.error.set(this.extractError(err));
    }
  }

  protected async onFileSelected(event: Event): Promise<void> {
    const producto = this.editingProducto();
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (!producto || !files || files.length === 0) return;

    this.uploadingImagen.set(true);
    this.formError.set('');
    try {
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append('file', file);
        const imagen = await firstValueFrom(
          this.http.post<Imagen>(`${environment.apiUrl}/productos/${producto.id}/imagenes`, formData),
        );
        const actualizado = { ...producto, imagenes: [...producto.imagenes, imagen] };
        this.editingProducto.set(actualizado);
      }
      await this.loadProductos();
    } catch (err) {
      this.formError.set(this.extractError(err));
    } finally {
      this.uploadingImagen.set(false);
      input.value = '';
    }
  }

  protected async eliminarImagen(imagenId: number): Promise<void> {
    const producto = this.editingProducto();
    if (!producto) return;
    if (!confirm('Eliminar esta imagen?')) return;

    try {
      await firstValueFrom(this.http.delete(`${environment.apiUrl}/productos/${producto.id}/imagenes/${imagenId}`));
      const actualizado = { ...producto, imagenes: producto.imagenes.filter((i) => i.id !== imagenId) };
      this.editingProducto.set(actualizado);
      await this.loadProductos();
    } catch (err) {
      this.formError.set(this.extractError(err));
    }
  }

  // ---------- CU09: imagen para el probador de realidad aumentada ----------
  // El motor (Decart) solo necesita la foto de la prenda + un prompt de
  // texto que arma el backend solo: no hace falta calibrar anclas de
  // hombros a mano (eso era del overlay 2D/3D anterior).

  protected async onArFileSelected(event: Event): Promise<void> {
    const producto = this.editingProducto();
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (!producto || !files || files.length === 0) return;

    const file = files[0];
    if (!['image/png', 'image/webp', 'image/jpeg'].includes(file.type)) {
      this.formError.set('La imagen debe ser JPG, PNG o WEBP.');
      input.value = '';
      return;
    }

    this.uploadingArImagen.set(true);
    this.formError.set('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const prendaAr = await firstValueFrom(
        this.http.post<PrendaAr>(`${environment.apiUrl}/productos/${producto.id}/ar-imagen`, formData),
      );
      this.editingProducto.set({ ...producto, prenda_ar: prendaAr });
      await this.loadProductos();
    } catch (err) {
      this.formError.set(this.extractError(err));
    } finally {
      this.uploadingArImagen.set(false);
      input.value = '';
    }
  }

  protected async eliminarPrendaAr(): Promise<void> {
    const producto = this.editingProducto();
    if (!producto) return;
    if (!confirm('Eliminar la imagen de realidad aumentada de este producto?')) return;

    try {
      await firstValueFrom(this.http.delete(`${environment.apiUrl}/productos/${producto.id}/ar-imagen`));
      this.editingProducto.set({ ...producto, prenda_ar: null });
      await this.loadProductos();
    } catch (err) {
      this.formError.set(this.extractError(err));
    }
  }

  // ---------- inventario por sucursal ----------

  private resetNuevoStockForm(): void {
    this.nStockSucursalId.set(this.catalogo().sucursales[0]?.id ?? null);
    this.nStockTallaId.set(this.catalogo().tallas[0]?.id ?? null);
    this.nStockColorId.set(this.catalogo().colores[0]?.id ?? null);
    this.nStockColorNuevo.set('');
    this.nStockCantidad.set('');
    this.stockError.set('');
  }

  private async loadInventario(productoId: number): Promise<void> {
    this.loadingInventario.set(true);
    try {
      const res = await firstValueFrom(
        this.http.get<Inventario[]>(`${environment.apiUrl}/productos/${productoId}/inventario`),
      );
      this.inventario.set(res);
    } catch {
      this.inventario.set([]);
    } finally {
      this.loadingInventario.set(false);
    }
  }

  protected async actualizarCantidad(inv: Inventario, valor: string): Promise<void> {
    const producto = this.editingProducto();
    const cantidad = Number(valor);
    if (!producto || Number.isNaN(cantidad) || cantidad < 0) return;

    try {
      const actualizado = await firstValueFrom(
        this.http.put<Inventario>(`${environment.apiUrl}/productos/${producto.id}/inventario/${inv.id}`, {
          cantidad,
        }),
      );
      this.inventario.update((lista) => lista.map((i) => (i.id === actualizado.id ? actualizado : i)));
    } catch (err) {
      this.stockError.set(this.extractError(err));
    }
  }

  protected async eliminarInventario(inv: Inventario): Promise<void> {
    const producto = this.editingProducto();
    if (!producto) return;
    if (!confirm(`Eliminar el stock de ${inv.sucursal_nombre} · ${inv.talla_codigo} · ${inv.color_nombre}?`)) return;

    this.stockError.set('');
    try {
      await firstValueFrom(
        this.http.delete(`${environment.apiUrl}/productos/${producto.id}/inventario/${inv.id}`),
      );
      this.inventario.update((lista) => lista.filter((i) => i.id !== inv.id));
    } catch (err) {
      this.stockError.set(this.extractError(err));
    }
  }

  protected async agregarStock(): Promise<void> {
    const producto = this.editingProducto();
    if (!producto || !this.nStockSucursalId() || !this.nStockTallaId() || !this.nStockColorId() || !this.nStockCantidad()) {
      this.stockError.set('Completa sucursal, talla, color y cantidad.');
      return;
    }
    if (this.nStockColorId() === this.colorOtro && !this.nStockColorNuevo().trim()) {
      this.stockError.set('Escribe el nombre del color nuevo.');
      return;
    }

    this.stockError.set('');
    this.savingStock.set(true);
    try {
      let colorId = this.nStockColorId();
      if (colorId === this.colorOtro) {
        const color = await firstValueFrom(
          this.http.post<Opcion>(`${environment.apiUrl}/productos/colores`, { nombre: this.nStockColorNuevo().trim() }),
        );
        this.catalogo.update((c) => ({ ...c, colores: [...c.colores, color].sort((a, b) => a.nombre.localeCompare(b.nombre)) }));
        colorId = color.id;
      }

      const nuevo = await firstValueFrom(
        this.http.post<Inventario>(`${environment.apiUrl}/productos/${producto.id}/inventario`, {
          sucursal_id: this.nStockSucursalId(),
          talla_id: this.nStockTallaId(),
          color_id: colorId,
          cantidad: Number(this.nStockCantidad()),
        }),
      );
      this.inventario.update((lista) => {
        const idx = lista.findIndex((i) => i.id === nuevo.id);
        if (idx === -1) return [...lista, nuevo];
        const copia = [...lista];
        copia[idx] = nuevo;
        return copia;
      });
      this.resetNuevoStockForm();
    } catch (err) {
      this.stockError.set(this.extractError(err));
    } finally {
      this.savingStock.set(false);
    }
  }

  private async loadCommon(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const catalogo = await firstValueFrom(this.http.get<CatalogoBase>(`${environment.apiUrl}/productos/catalogo-base`));
      this.catalogo.set(catalogo);
    } catch {
      this.error.set('No se pudo cargar categorias, temporadas, colecciones o proveedores.');
    }
    await this.loadProductos();
  }

  private async loadProductos(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const params: Record<string, string> = {};
      if (this.buscar().trim()) params['buscar'] = this.buscar().trim();
      const res = await firstValueFrom(this.http.get<Producto[]>(`${environment.apiUrl}/productos`, { params }));
      this.productos.set(res);
    } catch {
      this.error.set('No se pudo cargar los productos.');
    } finally {
      this.loading.set(false);
    }
  }

  private extractError(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail = err.error?.detail;
      if (typeof detail === 'string') return detail;
      if (err.status === 0) return 'No pudimos conectar con el servidor.';
    }
    return 'Ocurrio un error inesperado.';
  }
}
