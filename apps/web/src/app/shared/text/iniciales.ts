/** Iniciales del monograma de un nombre: hasta dos letras de las primeras
 * dos palabras, para cuando no hay foto real que mostrar. */
export function iniciales(nombre: string): string {
  return nombre
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((palabra) => palabra[0]?.toUpperCase() ?? '')
    .join('');
}
