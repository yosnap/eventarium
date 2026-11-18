// Comprueba los ficheros de traducción de la interfaz contra el español, que es la
// fuente: mismas claves y mismas variables `{{ }}` en cada idioma. Falla (código 1)
// si algo no cuadra, para que CI lo pare.
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const CARPETA = join(import.meta.dirname, '..', 'public', 'assets', 'i18n');
const ORIGEN = 'es-ES';
const VARIABLE = /\{\{\s*([^}]+?)\s*\}\}/g;

function aplanar(arbol, prefijo = '') {
  return Object.entries(arbol).flatMap(([clave, valor]) =>
    valor !== null && typeof valor === 'object'
      ? aplanar(valor, `${prefijo}${clave}.`)
      : [[`${prefijo}${clave}`, String(valor)]],
  );
}

const leer = (idioma) =>
  new Map(aplanar(JSON.parse(readFileSync(join(CARPETA, `${idioma}.json`), 'utf-8'))));
const variables = (texto) =>
  [...texto.matchAll(VARIABLE)]
    .map((m) => m[1])
    .sort()
    .join('|');

const origen = leer(ORIGEN);
const destinos = readdirSync(CARPETA)
  .filter((nombre) => nombre.endsWith('.json') && nombre !== `${ORIGEN}.json`)
  .map((nombre) => nombre.replace(/\.json$/, ''));

let errores = 0;
for (const idioma of destinos) {
  const destino = leer(idioma);
  const faltan = [...origen.keys()].filter((clave) => !destino.has(clave));
  const sobran = [...destino.keys()].filter((clave) => !origen.has(clave));
  const variablesDistintas = [...destino]
    .filter(
      ([clave, texto]) => origen.has(clave) && variables(texto) !== variables(origen.get(clave)),
    )
    .map(([clave]) => clave);
  const informar = (titulo, claves) => {
    if (claves.length > 0) {
      errores += claves.length;
      console.error(`✗ ${idioma}: ${titulo} (${claves.length})`);
      for (const clave of claves.slice(0, 20)) console.error(`    ${clave}`);
      if (claves.length > 20) console.error(`    … y ${claves.length - 20} más`);
    }
  };
  informar('faltan claves; ejecuta `pnpm i18n:traducir`', faltan);
  informar('claves que ya no existen en español', sobran);
  informar('variables {{ }} distintas del original', variablesDistintas);
  if (faltan.length + sobran.length + variablesDistintas.length === 0) {
    console.log(`✓ ${idioma}: ${destino.size} claves, al día con ${ORIGEN}`);
  }
}

// Texto escrito directamente en las plantillas o en atributos visibles: tiene que ir
// en `es-ES.json` para poder traducirse. Solo cuenta lo que parece texto para
// personas (acentos o varias palabras), no código ni marcas.
const MARCAS = new Set(['OpenStreetMap']);
const TEXTO = />\s*([^<>{}]*[A-Za-zÁÉÍÓÚáéíóúñÑ¿¡][^<>{}]*?)\s*</g;
const ATRIBUTO = /\s(?:aria-label|placeholder|title|alt)="([^"{]*[a-záéíóúñ]{3,}[^"]*)"/g;
const pareceTexto = (texto) =>
  !MARCAS.has(texto.trim()) &&
  !/\w\.\w/.test(texto) &&
  (/[áéíóúñ¿¡]/i.test(texto) || /[a-z]{2,}\s+[a-z]{2,}/i.test(texto));

function fuentes(carpeta) {
  return readdirSync(carpeta, { withFileTypes: true }).flatMap((entrada) => {
    const ruta = join(carpeta, entrada.name);
    if (entrada.isDirectory()) return fuentes(ruta);
    return ruta.endsWith('.ts') && !ruta.endsWith('.spec.ts') ? [ruta] : [];
  });
}

const literales = fuentes(join(import.meta.dirname, '..', 'src', 'app')).flatMap((fichero) => {
  const plantillas = [...readFileSync(fichero, 'utf-8').matchAll(/template:\s*`([\s\S]*?)`/g)];
  return plantillas
    .flatMap(([, plantilla]) => [...plantilla.matchAll(TEXTO), ...plantilla.matchAll(ATRIBUTO)])
    .filter((m) => pareceTexto(m[1]))
    .map((m) => `${fichero.split('/src/app/')[1]}: «${m[1].trim()}»`);
});
if (literales.length > 0) {
  errores += literales.length;
  console.error(`✗ texto literal en plantillas; pásalo a es-ES.json (${literales.length})`);
  for (const linea of literales) console.error(`    ${linea}`);
} else {
  console.log('✓ sin texto literal en las plantillas');
}

process.exit(errores > 0 ? 1 : 0);
