/**
 * Iniciales para un monograma: primera letra de nombre y apellidos, con el
 * correo como último recurso cuando falta todo. Lo usan el selector de
 * organizaciones y las fichas de ponente.
 */
export function monograma(first: string | null, last: string | null, fallback: string): string {
  const iniciales = [first?.trim()[0], last?.trim()[0]]
    .filter((letra): letra is string => !!letra)
    .map((letra) => letra.toUpperCase());
  if (iniciales.length > 0) {
    return iniciales.join('');
  }
  return fallback.slice(0, 2).toUpperCase();
}
