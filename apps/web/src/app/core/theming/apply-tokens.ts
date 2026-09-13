import { TOKENS_DE_PLANTILLA, PlantillaDeTema, TokensDePlantilla } from './theme-template.model';

/** Identidad del chrome de la web pública: se aplica al documento entero. */
const ID_ESTILO_PLATAFORMA = 'tema-plataforma';

/** Plantilla de la organización: se aplica solo a sus páginas de evento. */
const ID_ESTILO_ORGANIZACION = 'tema-organizacion';

/** Hoja del tema propio de un evento, por encima del de su organización. */
const ID_ESTILO_EVENTO = 'tema-evento';

/**
 * Marcador del ámbito de la organización. Las páginas de evento lo llevan en su
 * contenedor raíz, así que heredan los tokens de su plantilla sin que el resto
 * de la web (que se queda con los de plataforma) cambie.
 */
export const SELECTOR_AMBITO_ORGANIZACION = '[data-ambito="organizacion"]';

/**
 * Ámbito del **evento**.
 *
 * Va **dentro** del de organización en el árbol del DOM, así que su tema gana
 * por cascada sin necesidad de más especificidad: un evento que elige plantilla
 * la impone en sus páginas, y uno que no la elige deja pasar la de su
 * organización. Los tres ámbitos (plataforma, organización, evento) son el mismo
 * mecanismo con distinto selector, no tres sistemas.
 */
export const SELECTOR_AMBITO_EVENTO = '[data-ambito="evento"]';

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
 * Traduce los tokens de una plantilla al bloque de dos reglas que se inyecta en
 * `<head>`: el modo oscuro con el selector base y el claro con
 * `[data-theme="light"]`, en ese orden, para que el modo claro de la plantilla
 * gane al oscuro de la propia plantilla.
 *
 * `selector` es el ámbito al que se aplican: `:root` para la identidad de la
 * plataforma (el chrome) y un contenedor para la plantilla de la organización
 * (sus páginas de evento). Como las custom properties se heredan, redefinirlas
 * en un contenedor basta para scoping sin tocar cada componente.
 *
 * `''` si no hay plantilla (`theme` es `null`): no se inyecta nada y el ámbito
 * se queda con la base de reserva de `tokens.css`.
 */
export function brandingToStyleBlock(tema: PlantillaDeTema | null, selector: string): string {
  if (!tema) {
    return '';
  }
  const oscuro = bloqueDeDeclaraciones(tokensValidos(tema.tokens.dark));
  const claro = bloqueDeDeclaraciones(tokensValidos(tema.tokens.light));
  const selectorClaro = selectorDeModoClaro(selector);
  return `${selector}{${oscuro}}${selectorClaro}{${claro}}`;
}

/**
 * Selector del modo claro para un ámbito dado.
 *
 * El modo oscuro va en el selector base y el claro lo sobreescribe cuando el
 * documento lleva `data-theme="light"` (lo pone el conmutador de tema). Para
 * `:root` hay que escribirlo como `:root[data-theme="light"]` (compuesto, no
 * descendiente); para un contenedor, `[data-theme="light"] <contenedor>`.
 */
function selectorDeModoClaro(selector: string): string {
  if (selector === ':root') {
    return ':root[data-theme="light"]';
  }
  return `[data-theme="light"] ${selector}`;
}

function _inyectar(documento: Document, id: string, bloque: string): void {
  const existente = documento.getElementById(id);
  if (!bloque) {
    existente?.remove();
    return;
  }
  const estilo = existente ?? documento.createElement('style');
  estilo.id = id;
  estilo.textContent = bloque;
  if (!existente) {
    documento.head.appendChild(estilo);
  }
}

/**
 * Aplica la plantilla de la **plataforma** al documento entero: es la identidad
 * del chrome de la web pública (header, pie, botones), presente en cualquier
 * host. Si no hay plantilla de plataforma, el documento se queda con la base de
 * reserva de `tokens.css`.
 */
export function applyTokensDePlataforma(
  plataforma: { theme: PlantillaDeTema | null },
  documento: Document,
): void {
  _inyectar(documento, ID_ESTILO_PLATAFORMA, brandingToStyleBlock(plataforma.theme, ':root'));
}

/**
 * Aplica la plantilla de la **organización** a su propio ámbito.
 *
 * No se aplica al documento entero: el chrome es de plataforma, y una
 * organización solo pone su marca en sus páginas de evento. Se emite como una
 * regla con selector de contenedor, así que cualquier página de evento que se
 * marque con ese atributo hereda sus tokens sin que el resto de la web cambie.
 */
export function applyTokensDeOrganizacion(
  organizacion: { theme: PlantillaDeTema | null } | null,
  documento: Document,
): void {
  const bloque = brandingToStyleBlock(organizacion?.theme ?? null, SELECTOR_AMBITO_ORGANIZACION);
  _inyectar(documento, ID_ESTILO_ORGANIZACION, bloque);
}

/**
 * Aplica la plantilla propia de un **evento**, si la eligió.
 *
 * Sin plantilla no se inyecta nada, y eso es deliberado: el ámbito del evento
 * dejaría de emitir reglas y la cascada devolvería el tema de su organización,
 * que es exactamente lo que significa «heredar».
 */
export function applyTokensDeEvento(
  evento: { theme: PlantillaDeTema | null } | null,
  documento: Document,
): void {
  const bloque = brandingToStyleBlock(evento?.theme ?? null, SELECTOR_AMBITO_EVENTO);
  _inyectar(documento, ID_ESTILO_EVENTO, bloque);
}
