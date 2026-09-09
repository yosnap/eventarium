import { atributoDeTemaParaHtml, leerModoDeCookie } from './app/core/theming/theme-cookie';

/**
 * Pinta `data-theme` en el `<html>` del HTML ya renderizado, a partir de la cookie
 * `eventarium.tema` de la petición. **Anti-parpadeo por cookie leída en SSR, sin
 * ningún script inline**: `styles.css` resuelve `color-scheme` a partir de este mismo
 * atributo (`[data-theme='light'] { color-scheme: light; }`), así que pintarlo aquí
 * basta para que los dos —el fondo y los controles nativos— lleguen correctos en la
 * primera respuesta. Sin cookie o con `eventarium.tema=oscuro`, no se toca el HTML:
 * `tokens.css` ya pinta oscuro en `:root` por defecto.
 *
 * En su propio módulo, separado de `server.ts`: ese fichero construye
 * `AngularNodeAppEngine` en cuanto se importa (código de nivel superior), lo que exige
 * el manifiesto real del build de SSR y no se puede instanciar en un test unitario. La
 * función en sí no depende de nada de eso, así que vive aparte para poder probarla sin
 * arrastrar ese coste.
 */
// Captura la etiqueta raíz `<html ...>` completa, con cualesquiera atributos que
// lleve. No se ancla a `lang="es-ES"` literal: el build de producción de Angular
// (`inlineCriticalCss`, vía beasties) le añade `data-beasties-container` a esa misma
// etiqueta, y una coincidencia literal exacta deja de encajar en cuanto el build
// toca esos atributos — se comprobó en `serve:ssr:web` real, no solo en el spec.
const PATRON_ETIQUETA_HTML = /<html\b([^>]*)>/;

export function pintarTemaEnHtml(html: string, cabeceraCookie: string | undefined): string {
  const atributo = atributoDeTemaParaHtml(leerModoDeCookie(cabeceraCookie ?? null));
  if (!atributo) {
    return html;
  }
  const coincidencia = PATRON_ETIQUETA_HTML.exec(html);
  if (!coincidencia) {
    // No hay ninguna etiqueta `<html>` en absoluto: no es el caso esperado (los
    // atributos pueden variar, pero la etiqueta siempre debería existir). Fallo
    // ruidoso, no mudo — se serviría el HTML tal cual, sin `data-theme`, y solo se
    // notaría como parpadeo de tema en producción.
    if (typeof process !== 'undefined' && process.env['NODE_ENV'] !== 'production') {
      console.warn(
        'pintarTemaEnHtml: no se ha encontrado ninguna etiqueta <html> en el HTML ' +
          'renderizado; no se ha podido pintar data-theme.',
      );
    }
    return html;
  }
  const atributosActuales = coincidencia[1];
  const atributosSinTemaPrevio = atributosActuales.replace(/\s*data-theme="[^"]*"/, '');
  const etiquetaNueva = `<html${atributosSinTemaPrevio} data-theme="${atributo}">`;
  return html.slice(0, coincidencia.index) + etiquetaNueva + html.slice(coincidencia.index + coincidencia[0].length);
}
