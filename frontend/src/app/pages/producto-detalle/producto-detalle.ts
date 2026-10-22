import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AgregarCarrito } from '../../components/agregar-carrito/agregar-carrito';
import { ArFoto } from '../../components/ar-foto/ar-foto';
import { ArTryon } from '../../components/ar-tryon/ar-tryon';
import { Relacionados } from '../../components/relacionados/relacionados';
import { ReservaForm } from '../../components/reserva-form/reserva-form';
import { Product } from '../../data/products';
import { Auth } from '../../services/auth';
import { isAgotado, toArPrenda } from '../../services/catalogo-publico';
import { TiendaActiva } from '../../services/tienda-activa';
import { LoginRequerido } from '../../services/login-requerido';

interface PrendaArApi {
  url: string;
  ancla_hombro_izq_x: string;
  ancla_hombro_izq_y: string;
  ancla_hombro_der_x: string;
  ancla_hombro_der_y: string;
  ancla_torso_y: string;
}

interface ProductoPublico {
  id: number;
  tienda: string;
  tienda_nombre: string;
  tienda_logo: string | null;
  tienda_color: string;
  nombre: string;
  descripcion: string | null;
  precio: string;
  precio_original: string | null;
  marca_nombre: string;
  categoria_nombre: string;
  temporada_nombre: string;
  imagenes: string[];
  sucursales_disponibles: string[];
  prenda_ar: PrendaArApi | null;
}

const WHATSAPP_NUMERO = '59173766956';
const PLACEHOLDER_IMAGE = '/img/productos/producto-1.jpg';

function toProduct(p: ProductoPublico): Product {
  const price = Number(p.precio);
  const originalPrice = p.precio_original ? Number(p.precio_original) : undefined;
  const discountLabel =
    originalPrice && originalPrice > price ? `-${Math.round((1 - price / originalPrice) * 100)}%` : undefined;

  return {
    id: String(p.id),
    tienda: p.tienda,
    tiendaNombre: p.tienda_nombre,
    tiendaLogo: p.tienda_logo,
    tiendaColor: p.tienda_color,
    name: p.nombre,
    brand: p.marca_nombre,
    price,
    originalPrice: discountLabel ? originalPrice : undefined,
    discountLabel,
    image: p.imagenes[0] ?? PLACEHOLDER_IMAGE,
    gallery: p.imagenes.length ? p.imagenes : [PLACEHOLDER_IMAGE],
    category: p.categoria_nombre.toLowerCase(),
    categoryLabel: p.categoria_nombre,
    temporada: p.temporada_nombre,
    isNew: false,
    colors: [],
    sizes: [],
    branchesInStock: p.sucursales_disponibles,
    description: p.descripcion ?? undefined,
    // Mismo criterio que crear_ar_sesion en el backend: cae a la primera
    // foto de catalogo solo si es una URL absoluta (subida real), no la
    // placeholder relativa generica de antes de conectar el backend real.
    arPrenda: toArPrenda(p.prenda_ar),
    hasPhotos: !!p.prenda_ar || (p.imagenes[0]?.startsWith('http') ?? false),
  };
}

@Component({
  selector: 'app-producto-detalle',
  imports: [RouterLink, ArTryon, ArFoto, ReservaForm, AgregarCarrito, Relacionados],
  templateUrl: './producto-detalle.html',
  styleUrl: './producto-detalle.scss',
})
export class ProductoDetalle implements OnInit {
  // Tienda que vende el producto: su logo, su color y su catalogo.
  protected readonly tienda = inject(TiendaActiva);
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(Auth);
  private readonly loginRequerido = inject(LoginRequerido);

  protected readonly product = signal<Product | undefined>(undefined);
  protected readonly isAgotado = isAgotado;
  protected readonly selectedColor = signal<string | null>(null);
  protected readonly selectedSize = signal<string | null>(null);
  protected readonly activeImage = signal<string>('');
  protected readonly detallesOpen = signal(true);
  protected readonly arMenuAbierto = signal(false);
  protected readonly arAbierto = signal(false);
  protected readonly arFotoAbierto = signal(false);
  protected readonly reservaAbierta = signal(false);
  protected readonly carritoAbierto = signal(false);

  protected readonly whatsappUrl = computed(() => {
    const p = this.product();
    const mensaje = p
      ? `Hola, quiero consultar sobre: ${p.name}${this.selectedColor() ? ' - color ' + this.selectedColor() : ''}${this.selectedSize() ? ' - talla ' + this.selectedSize() : ''}`
      : 'Hola, quiero hacer una consulta.';
    return `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(mensaje)}`;
  });

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(async (params) => {
      const id = params.get('id') ?? '';
      try {
        const res = await firstValueFrom(
          this.http.get<ProductoPublico>(`${environment.apiUrl}/productos/publico/${id}`),
        );
        const found = toProduct(res);
        // Su marca, y relacionados y recomendaciones solo de la misma tienda.
        this.tienda.activar(found.tienda ?? null);
        this.product.set(found);
        this.selectedColor.set(found.colors[0]?.name ?? null);
        this.selectedSize.set(found.sizes[0] ?? null);
        this.activeImage.set(found.gallery[0] ?? found.image);
        this.continuarIntentoPendiente();
      } catch {
        this.product.set(undefined);
      }
    });
  }

  // Si el cliente llego aca con `?intent=...` (volviendo de /login despues
  // de que "agregar al carrito"/"reservar"/"probarme la prenda" lo mandaran
  // a iniciar sesion) y ya esta logueado, retoma esa misma accion en vez de
  // dejarlo con la ficha vacia y tener que repetir todo el paso. Se limpia
  // el query param al toque para que un refresh de la pagina no la reabra.
  private continuarIntentoPendiente(): void {
    const intent = this.route.snapshot.queryParamMap.get('intent');
    if (!intent || !this.auth.currentUser()) return;

    void this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true });

    if (intent === 'carrito') this.carritoAbierto.set(true);
    else if (intent === 'reserva') this.reservaAbierta.set(true);
    else if (intent === 'ar') this.arMenuAbierto.set(true);
  }

  // Sin sesion: en vez de mandar directo a /login, avisa que hace falta
  // iniciar sesion (modal global LoginRequerido) con la opcion de entrar o
  // crear una cuenta. La URL de vuelta lleva el intent, asi al volver se
  // retoma la misma accion (ver continuarIntentoPendiente).
  private pedirLoginConIntento(intent: 'carrito' | 'reserva' | 'ar'): void {
    const id = this.product()?.id ?? this.route.snapshot.paramMap.get('id');
    const acciones = {
      carrito: 'para anadir productos a tu carrito',
      reserva: 'para reservar este producto',
      ar: 'para probarte esta prenda con realidad aumentada',
    };
    this.loginRequerido.pedir(acciones[intent], `/producto/${id}?intent=${intent}`);
  }

  protected selectColor(name: string): void {
    this.selectedColor.set(name);
  }

  protected selectSize(size: string): void {
    this.selectedSize.set(size);
  }

  protected toggleArMenu(): void {
    // CU09: probarse una prenda (online o virtual) requiere sesion iniciada
    // -- asi queda registrado quien probo cada prenda para el dashboard de
    // administracion (P4 > CU09). Si no hay sesion, manda a loguearse (o
    // registrarse, desde ahi) en vez de abrir el menu de opciones.
    if (!this.auth.currentUser()) {
      this.pedirLoginConIntento('ar');
      return;
    }
    this.arMenuAbierto.set(!this.arMenuAbierto());
  }

  protected abrirArOnline(): void {
    this.arMenuAbierto.set(false);
    this.arAbierto.set(true);
  }

  protected cerrarAr(): void {
    this.arAbierto.set(false);
  }

  protected abrirArFoto(): void {
    this.arMenuAbierto.set(false);
    this.arFotoAbierto.set(true);
  }

  protected cerrarArFoto(): void {
    this.arFotoAbierto.set(false);
  }

  protected abrirReserva(): void {
    // CU10: igual que probarse la prenda, reservar requiere sesion
    // iniciada (la reserva queda ligada al cliente que la hizo).
    if (!this.auth.currentUser()) {
      this.pedirLoginConIntento('reserva');
      return;
    }
    this.reservaAbierta.set(true);
  }

  protected cerrarReserva(): void {
    this.reservaAbierta.set(false);
  }

  protected selectImage(src: string): void {
    this.activeImage.set(src);
  }

  protected addToCart(): void {
    const p = this.product();
    if (!p || isAgotado(p)) return;

    // CU11: el carrito ahora es real (backend), asociado al cliente -- igual
    // que probarse la prenda o reservar, hace falta sesion iniciada.
    if (!this.auth.currentUser()) {
      this.pedirLoginConIntento('carrito');
      return;
    }
    this.carritoAbierto.set(true);
  }

  protected cerrarCarrito(): void {
    this.carritoAbierto.set(false);
  }
}
