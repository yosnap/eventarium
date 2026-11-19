import { LOCALE_ID, Provider } from '@angular/core';

import { registrarDatosDeIdioma } from '../app/core/i18n/datos-de-idioma';

/**
 * Proveedores comunes a todos los tests.
 *
 * Fuera de la aplicación, Angular usa `en-US` como `LOCALE_ID`. La aplicación lo
 * resuelve siempre con el idioma de la visita, y los tests se escriben en el idioma
 * por defecto: un test que necesite otro idioma lo sobrescribe en su `TestBed`.
 */
registrarDatosDeIdioma();

const providers: Provider[] = [{ provide: LOCALE_ID, useValue: 'es-ES' }];

export default providers;
