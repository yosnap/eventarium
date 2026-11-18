import { Injectable } from '@angular/core';
import { Translation, TranslocoLoader } from '@jsverse/transloco';
import { Observable, from, of } from 'rxjs';

import esES from '../../../../public/assets/i18n/es-ES.json';
import { environment } from '../../../environments/environment';
import { IDIOMA_POR_DEFECTO, Idioma, esIdioma } from './idioma';
import { pseudoIdiomaPedido, pseudoTraduccion } from './pseudo-idioma';

/**
 * Traducciones de la interfaz.
 *
 * - El idioma por defecto va dentro del paquete principal: quien navega en español
 *   no espera ninguna descarga y el SSR no depende de una URL absoluta.
 * - Cada otro idioma es un chunk aparte (`import()`), del mismo origen y cacheable:
 *   quien navega en español no descarga el inglés.
 *
 * El mapa es cerrado e indexado por el catálogo: ningún valor del cliente decide qué
 * fichero se carga. Si un idioma no carga, se muestra en español en vez de romper la
 * página (en SSR, un error aquí sería un 500).
 */
const CARGADORES: Readonly<Partial<Record<Idioma, () => Promise<unknown>>>> = {
  'en-US': () => import('../../../../public/assets/i18n/en-US.json'),
};

function comoTraduccion(modulo: unknown): Translation {
  const valor = (modulo as { default?: unknown }).default ?? modulo;
  return (valor ?? {}) as Translation;
}

@Injectable({ providedIn: 'root' })
export class TraduccionesLoader implements TranslocoLoader {
  getTranslation(idioma: string): Observable<Translation> {
    if (!esIdioma(idioma)) {
      throw new Error(`«${idioma}» no es un idioma de la aplicación.`);
    }
    const cargar = CARGADORES[idioma];
    if (idioma === IDIOMA_POR_DEFECTO || !cargar) {
      if (idioma === IDIOMA_POR_DEFECTO && !environment.production && pseudoIdiomaPedido()) {
        return of(pseudoTraduccion(esES as Translation));
      }
      return of(idioma === IDIOMA_POR_DEFECTO ? (esES as Translation) : {});
    }
    return from(
      cargar().then(comoTraduccion, (error: unknown) => {
        console.error(`[i18n] no se han podido cargar los textos en «${idioma}»`, error);
        return {} as Translation;
      }),
    );
  }
}
