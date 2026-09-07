import { Injectable } from '@angular/core';
import { Translation, TranslocoLoader } from '@jsverse/transloco';
import { Observable, of } from 'rxjs';

import esES from '../../../../public/assets/i18n/es-ES.json';

/**
 * Traducciones incluidas en el paquete.
 *
 * Se importan en lugar de descargarlas por HTTP. Cargarlas por red obliga a construir
 * una URL absoluta durante el renderizado en servidor, y cualquier fallo ahí tumba la
 * página entera con «Unable to load translation». Al importarlas, servidor y navegador
 * usan exactamente lo mismo, no hay petición que falle y se ahorra una ida y vuelta
 * antes del primer pintado.
 *
 * El fichero JSON sigue siendo la única fuente: para añadir un idioma, se añade su
 * fichero y su entrada en este mapa.
 */
const TRADUCCIONES: Readonly<Record<string, Translation>> = {
  'es-ES': esES as Translation,
};

@Injectable({ providedIn: 'root' })
export class TraduccionesLoader implements TranslocoLoader {
  getTranslation(idioma: string): Observable<Translation> {
    const traduccion = TRADUCCIONES[idioma];
    if (!traduccion) {
      throw new Error(`No hay traducciones para «${idioma}».`);
    }
    // El contrato de Transloco espera un Observable, aunque el valor ya esté disponible.
    return of(traduccion);
  }
}
