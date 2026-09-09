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
const MARCADOR_HTML = '<html lang="es-ES">';

export function pintarTemaEnHtml(html: string, cabeceraCookie: string | undefined): string {
  const atributo = atributoDeTemaParaHtml(leerModoDeCookie(cabeceraCookie ?? null));
  if (!atributo) {
    return html;
  }
  if (!html.includes(MARCADOR_HTML)) {
    // Sustitución literal, no una expresión regular tolerante: si `index.html` cambia
    // el `lang` del `<html>` (o le añade otro atributo) esto deja de encajar y, sin
    // este aviso, el fallo sería mudo — se serviría el HTML tal cual, sin
    // `data-theme`, y solo se notaría como parpadeo de tema en producción.
    if (typeof process !== 'undefined' && process.env['NODE_ENV'] !== 'production') {
      console.warn(
        `pintarTemaEnHtml: no se ha encontrado «${MARCADOR_HTML}» en el HTML renderizado; ` +
          'no se ha podido pintar data-theme. Revisa si index.html cambió el <html> raíz.',
      );
    }
    return html;
  }
  return html.replace(MARCADOR_HTML, `<html lang="es-ES" data-theme="${atributo}">`);
}
