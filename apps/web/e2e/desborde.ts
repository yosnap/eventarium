import { expect, type Page } from '@playwright/test';

/** Un elemento que se sale por la derecha de la pantalla sin estar en un contenedor con scroll. */
interface Desborde {
  readonly selector: string;
  readonly derecha: number;
}

/**
 * Espera a que la página esté quieta y comprueba que no hay nada que obligue
 * a desplazarse en horizontal ni quede fuera por los bordes de la pantalla.
 *
 * Se ignora lo que está dentro de un contenedor que recorta o desplaza a
 * propósito (una tabla con scroll, un mapa). Para que eso no sirva de tapadera,
 * también falla si `html` o `body` recortan en horizontal: un
 * `overflow-x: hidden` global escondería el scroll sin arreglar el contenido.
 */
export async function esperarSinDesborde(page: Page, ruta: string): Promise<void> {
  // Con límite: el captcha (Turnstile) mantiene la red ocupada y la red en
  // reposo no llega nunca en las páginas que lo llevan.
  await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => undefined);
  // Las animaciones de entrada (GSAP) mueven elementos al cargar.
  await page.waitForTimeout(600);

  // El ancho configurado, no el del documento: en un móvil, si algo desborda,
  // el navegador ensancha la página entera y la aleja, y `clientWidth` crece
  // con ella (así es como «se ve pequeño y descuadrado» en Android).
  const ancho = page.viewportSize()?.width ?? 360;
  const resultado = await page.evaluate((ancho) => {
    const conScrollPropio = (el: Element): boolean => {
      for (let actual = el.parentElement; actual; actual = actual.parentElement) {
        const estilo = getComputedStyle(actual);
        if (estilo.overflowX !== 'visible') {
          return true;
        }
      }
      return false;
    };
    const describir = (el: Element): string => {
      const id = el.id ? `#${el.id}` : '';
      const clases = [...el.classList]
        .slice(0, 3)
        .map((c) => `.${c}`)
        .join('');
      const padre = el.parentElement?.tagName.toLowerCase() ?? '';
      return `${padre} > ${el.tagName.toLowerCase()}${id}${clases}`;
    };

    const desbordes: Desborde[] = [];
    for (const el of document.body.querySelectorAll('*')) {
      const caja = el.getBoundingClientRect();
      if (caja.width === 0 || caja.height === 0) continue;
      const estilo = getComputedStyle(el);
      if (estilo.visibility === 'hidden') continue;
      const padre = el.parentElement;
      const padreDesborda =
        padre !== null &&
        padre !== document.body &&
        padre.getBoundingClientRect().right > ancho + 1;
      // Por la izquierda solo cuenta lo que asoma en parte: lo que está entero
      // fuera (el enlace «Saltar al contenido») está escondido a propósito.
      const fuera = caja.right > ancho + 1 || (caja.left < -1 && caja.right > 0);
      if (fuera && !padreDesborda && !conScrollPropio(el)) {
        desbordes.push({ selector: describir(el), derecha: Math.round(caja.right) });
      }
    }
    const recortaGlobal = [document.documentElement, document.body].some(
      (el) => getComputedStyle(el).overflowX !== 'visible',
    );
    return {
      ancho,
      recortaGlobal,
      anchoDocumento: document.documentElement.scrollWidth,
      // Solo los más externos (sus hijos repetirían el mismo problema).
      desbordes: desbordes.slice(0, 8),
    };
  }, ancho);

  expect.soft(resultado.recortaGlobal, `${ruta}: html o body recortan en horizontal`).toBe(false);
  expect
    .soft(resultado.anchoDocumento, `${ruta}: la página se desplaza en horizontal`)
    .toBeLessThanOrEqual(resultado.ancho + 1);
  expect
    .soft(resultado.desbordes, `${ruta}: hay contenido cortado o fuera de la pantalla`)
    .toEqual([]);
}
