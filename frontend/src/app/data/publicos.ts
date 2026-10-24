// Para quién es una prenda (y para quién vende una boutique).
export type Publico = 'mujer' | 'hombre' | 'unisex' | 'nina' | 'nino' | 'bebe';

export const PUBLICOS: { id: Publico; etiqueta: string }[] = [
  { id: 'mujer', etiqueta: 'Mujer' },
  { id: 'hombre', etiqueta: 'Hombre' },
  { id: 'unisex', etiqueta: 'Unisex' },
  { id: 'nina', etiqueta: 'Niña' },
  { id: 'nino', etiqueta: 'Niño' },
  { id: 'bebe', etiqueta: 'Bebé' },
];

export const ETIQUETA_PUBLICO: Record<string, string> = Object.fromEntries(PUBLICOS.map((p) => [p.id, p.etiqueta]));

// Una prenda unisex también aparece al filtrar Mujer u Hombre.
export function coincidePublico(prenda: string | undefined, filtro: string | null): boolean {
  if (!filtro) return true;
  return prenda === filtro || (prenda === 'unisex' && (filtro === 'mujer' || filtro === 'hombre'));
}
