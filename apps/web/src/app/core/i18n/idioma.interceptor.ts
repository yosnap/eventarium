import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { environment } from '../../../environments/environment';
import { IDIOMA } from './idioma.service';

/** Si la petición va a la API propia (relativa en el navegador, interna en SSR). */
function vaALaApi(url: string): boolean {
  return url.startsWith(environment.apiPath) || url.startsWith(environment.serverApiBaseUrl);
}

/**
 * Pide a la API que responda en el idioma de la página, no en el del navegador:
 * una visita a `/en/…` recibe sus errores y textos en inglés aunque el navegador
 * esté configurado en otro idioma. No se manda a servicios de terceros.
 */
export const idiomaInterceptor: HttpInterceptorFn = (peticion, siguiente) => {
  if (!vaALaApi(peticion.url)) {
    return siguiente(peticion);
  }
  return siguiente(peticion.clone({ setHeaders: { 'Accept-Language': inject(IDIOMA) } }));
};
