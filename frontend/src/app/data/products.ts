export interface ProductColor {
  name: string;
  hex: string;
}

// Imagen con fondo transparente + anclas de hombros/torso (como fraccion
// 0-1 del ancho/alto de la imagen) para el probador con realidad aumentada
// (CU09). Ver backend/app/models/p3_catalogo.py::PrendaAr.
export interface ArPrenda {
  url: string;
  anclaHombroIzqX: number;
  anclaHombroIzqY: number;
  anclaHombroDerX: number;
  anclaHombroDerY: number;
  anclaTorsoY: number;
}

export interface Product {
  id: string;
  // Tienda que lo vende (subdominio) y su nombre.
  tienda?: string;
  tiendaNombre?: string;
  tiendaLogo?: string | null;
  tiendaColor?: string;
  name: string;
  brand?: string;
  price: number;
  originalPrice?: number;
  discountLabel?: string;
  image: string;
  gallery: string[];
  category: string;
  categoryLabel: string;
  // Para quién es: mujer, hombre, unisex, nina, nino o bebe.
  publico?: string;
  temporada?: string;
  isNew: boolean;
  colors: ProductColor[];
  sizes: string[];
  branchesInStock: string[];
  description?: string;
  arPrenda?: ArPrenda;
  // Tiene al menos una foto de catalogo (no el placeholder generico): el
  // probador con realidad aumentada (CU09) puede usarla como referencia
  // aunque el producto no tenga una imagen dedicada con fondo transparente
  // (arPrenda), asi que esto es lo que realmente habilita el boton.
  hasPhotos?: boolean;
}

// TODO: placeholder generico (fotos libres de Pexels + nombres inventados,
// sin marcas ajenas) mientras no tenemos el catalogo real conectado al
// backend (tabla Producto + Inventario). Colores, tallas y sucursales con
// stock son inventados: no hay variantes reales todavia.
export const PRODUCTS: Product[] = [
  {
    id: '1',
    name: 'Polera Negra Basica',
    brand: 'Nike',
    price: 120,
    image: '/img/productos/producto-1.jpg',
    gallery: ['/img/productos/producto-1.jpg'],
    category: 'poleras',
    categoryLabel: 'Poleras',
    isNew: true,
    colors: [
      { name: 'Negro', hex: '#1a1a1a' },
      { name: 'Blanco', hex: '#ffffff' },
    ],
    sizes: ['S', 'M', 'L', 'XL'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Norte'],
  },
  {
    id: '2',
    name: 'Polera Blanca Oversize',
    brand: 'Adidas',
    price: 130,
    image: '/img/productos/producto-2.jpg',
    gallery: ['/img/productos/producto-2.jpg'],
    category: 'poleras',
    categoryLabel: 'Poleras',
    isNew: true,
    colors: [
      { name: 'Blanco', hex: '#ffffff' },
      { name: 'Negro', hex: '#1a1a1a' },
    ],
    sizes: ['S', 'M', 'L', 'XL'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Las Palmas'],
  },
  {
    id: '3',
    name: 'Jean Slim Azul',
    brand: "Levi's",
    price: 250,
    image: '/img/productos/producto-3.jpg',
    gallery: ['/img/productos/producto-3.jpg'],
    category: 'pantalones',
    categoryLabel: 'Pantalones',
    isNew: true,
    colors: [{ name: 'Azul', hex: '#2b4a6f' }],
    sizes: ['30', '32', '34', '36'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Norte', 'Sucursal Las Palmas'],
  },
  {
    id: '4',
    name: 'Chaqueta de Cuero Negra',
    brand: 'Puma',
    price: 450,
    image: '/img/productos/producto-4.jpg',
    gallery: ['/img/productos/producto-4.jpg'],
    category: 'chalecos',
    categoryLabel: 'Chalecos',
    isNew: true,
    colors: [{ name: 'Negro', hex: '#1a1a1a' }],
    sizes: ['M', 'L', 'XL'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Las Palmas'],
  },
  {
    id: '5',
    name: 'Sudadera Gris Oversize',
    brand: 'Champion',
    price: 175,
    originalPrice: 350,
    discountLabel: '-50%',
    image: '/img/productos/descuento-1.jpg',
    gallery: ['/img/productos/descuento-1.jpg'],
    category: 'hoodie',
    categoryLabel: 'Hoodie',
    isNew: false,
    colors: [{ name: 'Gris', hex: '#9a9a9a' }],
    sizes: ['S', 'M', 'L', 'XL'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Norte'],
  },
  {
    id: '6',
    name: 'Gorra Negra Clasica',
    brand: 'New Balance',
    price: 96,
    originalPrice: 120,
    discountLabel: '-20%',
    image: '/img/productos/descuento-2.jpg',
    gallery: ['/img/productos/descuento-2.jpg'],
    category: 'accesorios',
    categoryLabel: 'Accesorios',
    isNew: false,
    colors: [{ name: 'Negro', hex: '#1a1a1a' }],
    sizes: ['Unica'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Las Palmas'],
  },
  {
    id: '7',
    name: 'Chompa Blanca Basica',
    brand: 'Calvin Klein',
    price: 224,
    originalPrice: 280,
    discountLabel: '-20%',
    image: '/img/productos/descuento-3.jpg',
    gallery: ['/img/productos/descuento-3.jpg'],
    category: 'hoodie',
    categoryLabel: 'Hoodie',
    isNew: false,
    colors: [{ name: 'Blanco', hex: '#ffffff' }],
    sizes: ['S', 'M', 'L'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Norte'],
  },
  {
    id: '8',
    name: 'Polera Grafica Negra',
    brand: 'Jordan',
    price: 160,
    image: '/img/productos/producto-1.jpg',
    gallery: ['/img/productos/producto-1.jpg'],
    category: 'poleras',
    categoryLabel: 'Poleras',
    isNew: false,
    colors: [{ name: 'Negro', hex: '#1a1a1a' }],
    sizes: ['S', 'M', 'L', 'XL'],
    branchesInStock: ['Sucursal Equipetrol', 'Sucursal Las Palmas', 'Sucursal Norte'],
  },
];

export function findProductById(id: string): Product | undefined {
  return PRODUCTS.find((p) => p.id === id);
}
