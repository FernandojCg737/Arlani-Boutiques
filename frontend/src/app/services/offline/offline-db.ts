import { Injectable } from '@angular/core';
import { DBSchema, IDBPDatabase, openDB } from 'idb';

// P4 offline (persistencia): IndexedDB del navegador. Sobrevive a cerrar y
// volver a abrir la app. Tres almacenes:
// - paquetes: lo descargado para trabajar sin conexión (CU11).
// - operaciones: ventas y reservas hechas sin conexión y su estado (CU12/CU13).
// - registro: cada intento de sincronización y su resultado (observabilidad).
// - sesion: token y dirección del backend del usuario, para que el service
//   worker (public/sw-arlani.js) sincronice aunque la app esté cerrada.
// - imagenes: las fotos de las prendas descargadas, para verlas sin conexión.

export interface VarianteLocal {
  talla_id: number;
  talla_codigo: string;
  color_id: number;
  color_nombre: string;
  stock: number;
  sucursal_id: number | null;
}

export interface ProductoLocal {
  producto_id: number;
  nombre: string;
  precio: string;
  imagen_url: string | null;
  categoria: string | null;
  variantes: VarianteLocal[];
}

export interface PaquetePersonal {
  empresa_id: number;
  empresa_nombre: string;
  sucursal: { id: number; nombre: string };
  descargado_en: string;
  productos: ProductoLocal[];
  clientes: { id: number; nombre: string; email: string }[];
}

export interface TiendaLocal {
  empresa_id: number;
  nombre: string;
  logo_url: string | null;
  sucursales: { id: number; nombre: string }[];
  productos: ProductoLocal[];
  acepta_contra_entrega?: boolean;
}

export interface CatalogoCliente {
  descargado_en: string;
  tiendas: TiendaLocal[];
  direcciones?: { id: number; alias: string; direccion: string }[];
}

export interface PaqueteGuardado {
  clave: string;
  usuario_id: number;
  descargado_en: string;
  datos: PaquetePersonal | CatalogoCliente;
}

export type EstadoOperacion =
  | 'pendiente'
  | 'enviando'
  | 'confirmada'
  | 'conflicto'
  | 'rechazada'
  | 'resuelta'
  | 'anulada'
  | 'error'
  // Compras del cliente sin conexión.
  | 'por_pagar'
  | 'sin_stock'
  | 'pagada'
  | 'cancelada';

export interface ItemLocal {
  producto_id: number;
  talla_id: number;
  color_id: number;
  cantidad: number;
  precio: string;
  producto_nombre: string;
  talla: string;
  color: string;
}

export interface OperacionLocal {
  uuid: string;
  usuario_id: number;
  tipo: 'venta' | 'reserva' | 'pedido';
  empresa_nombre: string;
  sucursal_id: number;
  sucursal_nombre: string;
  registrada_en: string;
  cliente_id: number | null;
  cliente_nombre: string | null;
  factura_nombre: string | null;
  factura_nit: string | null;
  horario_atencion: string | null;
  // Compra del cliente: retiro o envío, y si paga en línea o contra entrega.
  entrega?: 'retiro' | 'envio';
  direccion_id?: number | null;
  forma_pago?: 'en_linea' | 'contra_entrega' | null;
  items: ItemLocal[];
  total: number;
  estado: EstadoOperacion;
  mensaje: string | null;
  venta_id: number | null;
  reserva_id: number | null;
  intentos: number;
  ultimo_intento: string | null;
}

export interface RegistroSync {
  id?: number;
  usuario_id: number;
  fecha: string;
  enviadas: number;
  confirmadas: number;
  conflictos: number;
  rechazadas: number;
  errores: number;
  detalle: string;
}

export interface SesionSync {
  usuario_id: number;
  token: string;
  api: string;
}

interface ArlaniOfflineDB extends DBSchema {
  paquetes: { key: string; value: PaqueteGuardado };
  operaciones: { key: string; value: OperacionLocal; indexes: { usuario: number } };
  registro: { key: number; value: RegistroSync; indexes: { usuario: number } };
  sesion: { key: number; value: SesionSync };
  imagenes: { key: string; value: { url: string; blob: Blob } };
}

@Injectable({ providedIn: 'root' })
export class OfflineDb {
  private db: Promise<IDBPDatabase<ArlaniOfflineDB>> | null = null;

  private abrir(): Promise<IDBPDatabase<ArlaniOfflineDB>> {
    this.db ??= openDB<ArlaniOfflineDB>('arlani-offline', 3, {
      upgrade(db, version) {
        if (version < 1) {
          db.createObjectStore('paquetes', { keyPath: 'clave' });
          db.createObjectStore('operaciones', { keyPath: 'uuid' }).createIndex('usuario', 'usuario_id');
          db.createObjectStore('registro', { keyPath: 'id', autoIncrement: true }).createIndex('usuario', 'usuario_id');
        }
        if (version < 2) db.createObjectStore('sesion', { keyPath: 'usuario_id' });
        if (version < 3) db.createObjectStore('imagenes', { keyPath: 'url' });
      },
    });
    return this.db;
  }

  async guardarSesion(sesion: SesionSync): Promise<void> {
    await (await this.abrir()).put('sesion', sesion);
  }

  async borrarSesiones(): Promise<void> {
    await (await this.abrir()).clear('sesion');
  }

  async imagen(url: string): Promise<Blob | undefined> {
    return (await (await this.abrir()).get('imagenes', url))?.blob;
  }

  async guardarImagen(url: string, blob: Blob): Promise<void> {
    await (await this.abrir()).put('imagenes', { url, blob });
  }

  async guardarPaquete(p: PaqueteGuardado): Promise<void> {
    await (await this.abrir()).put('paquetes', p);
  }

  async paquete(clave: string): Promise<PaqueteGuardado | undefined> {
    return (await this.abrir()).get('paquetes', clave);
  }

  async paquetesDe(usuarioId: number): Promise<PaqueteGuardado[]> {
    return (await (await this.abrir()).getAll('paquetes')).filter((p) => p.usuario_id === usuarioId);
  }

  async operaciones(usuarioId: number): Promise<OperacionLocal[]> {
    const ops = await (await this.abrir()).getAllFromIndex('operaciones', 'usuario', usuarioId);
    return ops.sort((a, b) => b.registrada_en.localeCompare(a.registrada_en));
  }

  async guardarOperacion(op: OperacionLocal): Promise<void> {
    await (await this.abrir()).put('operaciones', op);
  }

  async registrar(r: RegistroSync): Promise<void> {
    await (await this.abrir()).add('registro', r);
  }

  async registro(usuarioId: number): Promise<RegistroSync[]> {
    const filas = await (await this.abrir()).getAllFromIndex('registro', 'usuario', usuarioId);
    return filas.reverse().slice(0, 30);
  }
}
