import { Translation } from '@jsverse/transloco';

const ACENTOS: Readonly<Record<string, string>> = {
  a: 'á',
  e: 'ë',
  i: 'î',
  o: 'ö',
  u: 'ü',
  A: 'Å',
  E: 'É',
  I: 'Î',
  O: 'Ö',
  U: 'Ü',
  c: 'ç',
  n: 'ñ',
  s: 'š',
  y: 'ý',
  z: 'ž',
};

/**
 * Pseudo-idioma de desarrollo: acentúa cada letra y alarga el texto un 40 %, entre
 * corchetes. Sirve para ver, sin esperar a ninguna traducción, qué texto está escrito
 * a mano en las plantillas (sale sin transformar) y dónde se desborda la maqueta con
 * textos más largos que el español, como suelen ser el alemán o el francés.
 *
 * Respeta las variables `{{ }}` y las etiquetas HTML.
 */
export function pseudoTexto(texto: string): string {
  const partes = texto.split(/(\{\{[^}]*\}\}|<[^>]+>)/g);
  const transformado = partes
    .map((parte, indice) =>
      indice % 2 === 1 ? parte : parte.replace(/[a-zA-Z]/g, (letra) => ACENTOS[letra] ?? letra),
    )
    .join('');
  const relleno = '·'.repeat(Math.ceil(texto.length * 0.4));
  return `[${transformado}${relleno}]`;
}

export function pseudoTraduccion(traduccion: Translation): Translation {
  return Object.fromEntries(
    Object.entries(traduccion).map(([clave, valor]) => [
      clave,
      typeof valor === 'string' ? pseudoTexto(valor) : pseudoTraduccion(valor as Translation),
    ]),
  );
}

/** Solo en el navegador y con `?pseudo` en la URL. Quien llama lo limita a desarrollo. */
export function pseudoIdiomaPedido(): boolean {
  return typeof location !== 'undefined' && new URLSearchParams(location.search).has('pseudo');
}
