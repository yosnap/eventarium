import { LOCALES_DE_CUENTA, LocaleDeCuenta } from './locale-de-cuenta';

/**
 * Idiomas de la aplicación y cómo se elige el de cada visita.
 *
 * El catálogo es el mismo que acepta la API (`LOCALES_DE_CUENTA`, espejo de
 * `apps/api/app/core/locale.py`). Todo lo que decide qué idioma se carga (prefijo
 * de URL, cookie, ficheros de traducción) sale de mapas cerrados indexados por
 * este catálogo: ningún valor que llegue del cliente elige un fichero.
 */
export type Idioma = LocaleDeCuenta;

export const IDIOMAS: readonly Idioma[] = LOCALES_DE_CUENTA;

export const IDIOMA_POR_DEFECTO: Idioma = 'es-ES';

/**
 * Primer segmento de las URL públicas en cada idioma. El idioma por defecto va
 * sin prefijo: las URL que ya existen no cambian.
 */
export const PREFIJO_DE_IDIOMA: Readonly<Record<Idioma, string>> = {
  'es-ES': '',
  'en-US': 'en',
};

/**
 * Rutas solo de cliente que siguen el idioma de la cuenta (cookie) en vez del
 * prefijo de la URL: los paneles y lo que depende de la sesión. Nunca una página
 * pública, cuyo idioma tiene que poder leerlo un buscador en la URL.
 */
const RUTAS_CON_IDIOMA_DE_CUENTA = [
  'dashboard',
  'admin',
  'espacio-de-trabajo',
  'oauth',
  'vista-previa',
] as const;

export const NOMBRE_COOKIE_IDIOMA = 'eventarium.idioma';

const UN_ANIO_EN_SEGUNDOS = 60 * 60 * 24 * 365;

export function esIdioma(valor: string | null | undefined): valor is Idioma {
  return (IDIOMAS as readonly string[]).includes(valor ?? '');
}

function primerSegmento(ruta: string): string {
  return ruta.replace(/^\/+/, '').split(/[/?#]/, 1)[0] ?? '';
}

/** Idioma que indica el prefijo de la ruta, o `null` si no lleva ninguno. */
export function idiomaDelPrefijo(ruta: string): Idioma | null {
  const segmento = primerSegmento(ruta);
  if (!segmento) {
    return null;
  }
  return IDIOMAS.find((idioma) => PREFIJO_DE_IDIOMA[idioma] === segmento) ?? null;
}

export function sigueIdiomaDeCuenta(ruta: string): boolean {
  return (RUTAS_CON_IDIOMA_DE_CUENTA as readonly string[]).includes(primerSegmento(ruta));
}

/** Busca la cookie de idioma en una cabecera `Cookie`; `null` si no hay o no es válida. */
export function leerIdiomaDeCookie(cabeceraCookie: string | null | undefined): Idioma | null {
  if (!cabeceraCookie) {
    return null;
  }
  for (const parte of cabeceraCookie.split(';')) {
    const indice = parte.indexOf('=');
    if (indice !== -1 && parte.slice(0, indice).trim() === NOMBRE_COOKIE_IDIOMA) {
      const valor = parte.slice(indice + 1).trim();
      return esIdioma(valor) ? valor : null;
    }
  }
  return null;
}

/** Cadena completa para `document.cookie`. */
export function serializarCookieDeIdioma(idioma: Idioma): string {
  return `${NOMBRE_COOKIE_IDIOMA}=${idioma}; Path=/; Max-Age=${UN_ANIO_EN_SEGUNDOS}; SameSite=Lax`;
}

/**
 * Idioma de una visita:
 * 1. el prefijo de la URL, si lo hay;
 * 2. en los paneles, la cookie con el idioma de la cuenta;
 * 3. si no, el idioma por defecto.
 *
 * Una página pública sin prefijo es siempre del idioma por defecto, tenga la
 * persona la cookie que tenga: su URL canónica no puede cambiar de idioma.
 */
export function resolverIdioma(ruta: string, cabeceraCookie: string | null | undefined): Idioma {
  const delPrefijo = idiomaDelPrefijo(ruta);
  if (delPrefijo) {
    return delPrefijo;
  }
  if (sigueIdiomaDeCuenta(ruta)) {
    return leerIdiomaDeCookie(cabeceraCookie) ?? IDIOMA_POR_DEFECTO;
  }
  return IDIOMA_POR_DEFECTO;
}

/** Nombre de cada idioma en ese mismo idioma, para el selector. */
export const NOMBRE_DEL_IDIOMA: Readonly<Record<Idioma, string>> = {
  'es-ES': 'Español',
  'en-US': 'English',
};
