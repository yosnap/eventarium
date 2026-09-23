import DOMPurify from 'dompurify';
import { marked } from 'marked';

/**
 * Lista blanca explícita del contenido legal: párrafos, apartados (`h2`/`h3`:
 * un documento legal se organiza por secciones; `h1` no, que es el título de
 * la página), negrita/cursiva, listas y enlaces. Nunca `<script>`, `<iframe>`
 * ni atributos `on*` — `ALLOWED_ATTR` ni siquiera los declara, así que
 * DOMPurify los descarta sin necesidad de una lista negra.
 */
const ETIQUETAS_PERMITIDAS = [
  'p',
  'h2',
  'h3',
  'strong',
  'em',
  'b',
  'i',
  'ul',
  'ol',
  'li',
  'a',
  'br',
];
const ATRIBUTOS_PERMITIDOS = ['href'];

marked.setOptions({ async: false, gfm: true, breaks: false });

/**
 * Markdown → HTML saneado.
 *
 * Solo se llama desde el navegador (nunca en SSR, ver `legal-page.ts`):
 * `DOMPurify` necesita un `window` con DOM real, que Node no tiene sin una
 * dependencia adicional (`jsdom`) que solo haría falta para este único caso.
 * Mientras no se ejecuta esta función, el contenido se muestra como texto
 * plano interpolado por Angular (siempre escapado, nunca HTML), así que un
 * `<script>` guardado en el contenido legal no se ejecuta ni antes ni después
 * de que esta función corra.
 */
// INVARIANTE: nunca bindees `[innerHTML]` con texto de organización (contenido
// legal, políticas del organizador, campos libres, lo que sea que edite alguien
// fuera del equipo). Se pinta siempre con `<app-markdown-seguro>`
// (`markdown-seguro.ts`), el único consumidor de esta función; un test recorre
// `src/app` para que no aparezca otro `[innerHTML]` con ese contenido.
export function markdownToSafeHtml(markdown: string): string {
  const html = marked.parse(markdown, { async: false }) as string;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ETIQUETAS_PERMITIDAS,
    ALLOWED_ATTR: ATRIBUTOS_PERMITIDOS,
  });
}
