/**
 * Cookie de la preferencia de modo oscuro/claro, compartida entre cliente y SSR.
 *
 * `SameSite=Lax`, sin `HttpOnly` (el cliente también la lee y la escribe), caducidad
 * larga. Concentrar aquí el nombre, el formato y el parseo evita que `server.ts` y
 * `ThemeModeService` diverjan (DRY): los dos leen la misma cabecera `Cookie` con las
 * mismas reglas.
 */

export const NOMBRE_COOKIE_TEMA = 'eventarium.tema';

export type ModoDeTema = 'oscuro' | 'claro';

const UN_ANIO_EN_SEGUNDOS = 60 * 60 * 24 * 365;

/**
 * Busca `eventarium.tema` en una cabecera `Cookie` (`clave=valor; clave2=valor2`).
 *
 * Devuelve `null` si la cookie no está presente, para que quien llama pueda distinguir
 * «no hay preferencia guardada» (y decidir su propio valor por defecto, p. ej.
 * `prefers-color-scheme`) de «hay preferencia y es oscura». Un valor presente pero
 * distinto de `claro` se trata como oscuro: no hay un tercer modo válido.
 */
export function leerModoDeCookieOpcional(
  cabeceraCookie: string | null | undefined,
): ModoDeTema | null {
  if (!cabeceraCookie) {
    return null;
  }
  for (const parte of cabeceraCookie.split(';')) {
    const indice = parte.indexOf('=');
    if (indice === -1) {
      continue;
    }
    const clave = parte.slice(0, indice).trim();
    if (clave !== NOMBRE_COOKIE_TEMA) {
      continue;
    }
    const valor = parte.slice(indice + 1).trim();
    return valor === 'claro' ? 'claro' : 'oscuro';
  }
  return null;
}

/** Igual que `leerModoDeCookieOpcional`, pero con oscuro como valor por defecto. */
export function leerModoDeCookie(cabeceraCookie: string | null | undefined): ModoDeTema {
  return leerModoDeCookieOpcional(cabeceraCookie) ?? 'oscuro';
}

/** Cadena completa para `document.cookie` o para la cabecera `Set-Cookie`. */
export function serializarCookieDeTema(modo: ModoDeTema): string {
  return `${NOMBRE_COOKIE_TEMA}=${modo}; Path=/; Max-Age=${UN_ANIO_EN_SEGUNDOS}; SameSite=Lax`;
}

/**
 * Atributo `data-theme` que corresponde a un modo, o `null` si es el modo por defecto
 * (oscuro) y por tanto no hace falta ningún atributo: `tokens.css` ya pinta oscuro en
 * `:root` sin necesidad de `[data-theme]`.
 */
export function atributoDeTemaParaHtml(modo: ModoDeTema): 'light' | null {
  return modo === 'claro' ? 'light' : null;
}
