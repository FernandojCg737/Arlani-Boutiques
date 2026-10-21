// Boutiques (empresas) que venden con Arlani. El carrusel de la portada ya las
// lee del backend (GET /tiendas); esta lista fija queda para cuando el
// servidor no responde y para el carrito, que todavía agrupa todo en la
// boutique original.
export interface Boutique {
  id: string;
  nombre: string;
  logo: string;
  ciudad: string;
  // Dónde está su catálogo de productos.
  ruta: string;
}

export const BOUTIQUES: Boutique[] = [
  {
    id: 'atelier-aranier',
    nombre: 'Atelier Aranier',
    logo: '/img/logo.png',
    ciudad: 'Santa Cruz',
    ruta: '/tienda-atelier-aranier',
  },
];
