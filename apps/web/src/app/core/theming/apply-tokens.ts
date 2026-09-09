import { Branding } from './branding.model';
import { TOKENS_DE_PLANTILLA, TokensDePlantilla } from './theme-template.model';

const ID_ESTILO = 'tema-organizacion';

/** Hex de 6 dígitos u `oklch()`: los dos formatos que también valida el backend. */
const FORMATO_HEX = /^#[0-9a-f]{6}$/i;
const FORMATO_OKLCH = /^oklch\(\s*[\d.]+%\s+[\d.]+\s+[\d.]+\s*(?:\/\s*[\d.]+%?)?\s*\)$/i;

/**
 * `--shadow-md`/`--shadow-lg` son el único par de tokens de plantilla cuyo valor no es
 * un color suelto, sino un `box-shadow` completo con un color `oklch()` embebido (así
 * es como los consume `shared/ui/card.ts` vía el alias `--shadow-card`). El resto de
 * la lista blanca exige hex o `oklch()` exactos.
 */
const TOKENS_DE_SOMBRA = new Set(['shadow-md', 'shadow-lg']);
const FORMATO_SOMBRA_CON_OKLCH = /oklch\(\s*[\d.]+%\s+[\d.]+\s+[\d.]+\s*(?:\/\s*[\d.]+%?)?\s*\)/i;

/**
 * Un valor de plantilla acaba dentro de una hoja de estilo, así que se exige un
 * formato de color admitido antes de escribirlo. Defensa en profundidad: el backend ya
 * valida lista blanca y formato, pero el cliente no depende de ello. Un token que no
 * pasa esto no se escribe, y el modo se cae al valor de reserva de `tokens.css`.
 */
function esValorSeguro(nombreToken: string, valor: unknown): valor is string {
  if (typeof valor !== 'string' || valor.length === 0 || valor.length > 300) {
    return false;
  }
  if (/[;{}<>]/.test(valor) || /url\s*\(/i.test(valor) || /expression\s*\(/i.test(valor)) {
    return false;
  }
  if (TOKENS_DE_SOMBRA.has(nombreToken)) {
    return FORMATO_SOMBRA_CON_OKLCH.test(valor);
  }
  return FORMATO_HEX.test(valor) || FORMATO_OKLCH.test(valor);
}

/** Filtra un juego de tokens de un modo por la lista blanca + el formato admitido. */
function tokensValidos(tokens: TokensDePlantilla): Record<string, string> {
  const validos: Record<string, string> = {};
  for (const nombre of TOKENS_DE_PLANTILLA) {
    const valor = tokens[nombre];
    if (esValorSeguro(nombre, valor)) {
      validos[nombre] = valor;
    }
  }
  return validos;
}

function bloqueDeDeclaraciones(tokens: Record<string, string>): string {
  return Object.entries(tokens)
    .map(([nombre, valor]) => `--${nombre}:${valor};`)
    .join('');
}

/**
 * Traduce `branding.theme.tokens` al bloque de dos reglas que se inyecta en `<head>`:
 * `:root{…}` con el modo oscuro y `[data-theme="light"]{…}` con el claro, en ese
 * orden, para que el modo claro de la plantilla gane al oscuro de la propia plantilla.
 * `''` si no hay ninguna plantilla (branding.theme es `null`): no se inyecta nada y la
 * aplicación se queda con la base de reserva de `tokens.css`.
 */
export function brandingToStyleBlock(branding: Branding): string {
  if (!branding.theme) {
    return '';
  }
  const oscuro = bloqueDeDeclaraciones(tokensValidos(branding.theme.tokens.dark));
  const claro = bloqueDeDeclaraciones(tokensValidos(branding.theme.tokens.light));
  return `:root{${oscuro}}[data-theme="light"]{${claro}}`;
}

/**
 * Aplica la plantilla de tema de la organización al documento.
 *
 * No se puede aplicar como estilo inline sobre `<html>` (`el.style.setProperty`): un
 * valor inline no distingue entre `:root` y `[data-theme="light"]`, así que cualquier
 * organización con plantilla propia dejaría muerto el conmutador de tema. En su lugar
 * se inyecta un `<style id="tema-organizacion">` en `<head>`, después de las hojas del
 * build, así que sus reglas ganan a las homónimas de `tokens.css` con la misma
 * especificidad. Si `branding.theme` es `null`, no se inyecta nada.
 */
export function applyTokens(branding: Branding, documento: Document): void {
  const bloque = brandingToStyleBlock(branding);
  const existente = documento.getElementById(ID_ESTILO);
  if (!bloque) {
    existente?.remove();
    return;
  }
  const estilo = existente ?? documento.createElement('style');
  estilo.id = ID_ESTILO;
  estilo.textContent = bloque;
  if (!existente) {
    documento.head.appendChild(estilo);
  }
}
