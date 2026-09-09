import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Entregable 0 de la fase de fundamentos del sistema de diseño.
 *
 * Sin esto, jsdom no tiene ninguna variable CSS de tema: `data-theme="light"` en un
 * fixture no cambiaría nada, y axe informaría `color-contrast` como `incomplete`, no
 * como `violation` (`esperarSinViolacionesDeAccesibilidad` solo mira `violations`).
 *
 * Un `import '../styles/tokens.css'` normal no basta aquí: el builder de test
 * (`@angular/build:unit-test`) extrae las hojas cargadas por `setupFiles` a un chunk
 * `.css` aparte que nada inyecta en el documento de jsdom (verificado: con solo el
 * `import`, `document.head` queda vacío y `getComputedStyle` no ve ninguna variable).
 * Por eso se leen los ficheros de disco y se inyectan a mano como `<style>` en
 * `document.head`, que es donde jsdom sí resuelve custom properties vía
 * `getComputedStyle`. Se omite `font-faces.css` a propósito (ver ese fichero): solo
 * hace falta que las variables de tema existan, no los binarios de las fuentes.
 *
 * **Idempotente a propósito.** Verificado: el builder reejecuta este `setupFile` más
 * de una vez sobre el mismo `document` compartido dentro de un mismo proceso de test
 * (con la suite completa, `document.head` llegaba a acumular hasta 3 copias de cada
 * hoja). Las copias duplicadas no son solo ruido: se ha observado que provocan lecturas
 * de `getComputedStyle` inconsistentes (`--bg` sin cambiar con `data-theme="light"` en
 * una fracción de las ejecuciones). Marcar el documento tras la primera inyección evita
 * la duplicación sea cual sea el motivo por el que este módulo se vuelva a evaluar.
 */
const MARCA = 'data-tokens-de-test-inyectados';

/**
 * Rutas absolutas a partir de `import.meta.dirname` (mismo patrón que
 * `apps/web/src/server.ts` para su carpeta de build), no del CWD del proceso:
 * `readFileSync('src/styles/...')` solo encuentra el fichero si el test runner se
 * invoca con el CWD puesto en `apps/web`, y rompe la suite entera con un `ENOENT`
 * si se ejecuta desde la raíz del monorepo.
 */
const DIRECTORIO_DE_ESTILOS = join(import.meta.dirname, '../styles');

if (!document.documentElement.hasAttribute(MARCA)) {
  const HOJAS = ['tokens.css', 'typography.css'];
  for (const hoja of HOJAS) {
    const estilo = document.createElement('style');
    estilo.textContent = readFileSync(join(DIRECTORIO_DE_ESTILOS, hoja), 'utf-8');
    document.head.appendChild(estilo);
  }
  document.documentElement.setAttribute(MARCA, '');
}
