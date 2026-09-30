/**
 * Etiquetas de un evento: mismas reglas que `normalizar_etiquetas` del API
 * (`apps/api/app/modules/events/categories.py`). Aquí solo se validan y
 * normalizan para avisar antes de enviar; la API vuelve a comprobarlas.
 */

export const MAX_ETIQUETAS = 5;
export const LONGITUD_MIN_ETIQUETA = 2;
export const LONGITUD_MAX_ETIQUETA = 30;

/** Letras (con tildes, ñ, ü), números, espacios y guiones; sin signos ni emoji. */
const PATRON_ETIQUETA = /^[a-z0-9áéíóúüñ]+(?:[ -][a-z0-9áéíóúüñ]+)*$/;

export type ErrorDeEtiquetas =
  | { readonly tipo: 'longitud'; readonly etiqueta: string }
  | { readonly tipo: 'caracteres'; readonly etiqueta: string }
  | { readonly tipo: 'demasiadas' };

export interface EtiquetasAnalizadas {
  readonly etiquetas: readonly string[];
  readonly error: ErrorDeEtiquetas | null;
}

/** Texto separado por comas → etiquetas en minúsculas, sin blancos de más ni repetidas. */
export function analizarEtiquetas(texto: string): EtiquetasAnalizadas {
  const limpias: string[] = [];
  for (const original of texto.split(',')) {
    const etiqueta = original.trim().toLowerCase().replace(/\s+/g, ' ');
    if (!etiqueta) {
      continue;
    }
    if (etiqueta.length < LONGITUD_MIN_ETIQUETA || etiqueta.length > LONGITUD_MAX_ETIQUETA) {
      return { etiquetas: limpias, error: { tipo: 'longitud', etiqueta } };
    }
    if (!PATRON_ETIQUETA.test(etiqueta)) {
      return { etiquetas: limpias, error: { tipo: 'caracteres', etiqueta } };
    }
    if (!limpias.includes(etiqueta)) {
      limpias.push(etiqueta);
    }
  }
  if (limpias.length > MAX_ETIQUETAS) {
    return { etiquetas: limpias, error: { tipo: 'demasiadas' } };
  }
  return { etiquetas: limpias, error: null };
}
