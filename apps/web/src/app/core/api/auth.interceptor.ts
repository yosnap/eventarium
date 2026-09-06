import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';

import { AuthService } from '../auth/auth.service';

/** Rutas de autenticación: no llevan token y no deben reintentarse tras un 401. */
const RUTAS_DE_AUTH = ['/auth/login', '/auth/refresh', '/auth/logout'];

/**
 * Añade el access token y, ante un 401, lo renueva **una sola vez**.
 *
 * El reintento único es intencionado: si el refresh también falla, insistir solo
 * produciría un bucle de peticiones contra un servidor que ya ha dicho que no.
 */
export const authInterceptor: HttpInterceptorFn = (peticion, siguiente) => {
  const auth = inject(AuthService);

  if (RUTAS_DE_AUTH.some((ruta) => peticion.url.includes(ruta))) {
    return siguiente(peticion);
  }

  const conToken = (token: string | null) =>
    token
      ? peticion.clone({ setHeaders: { Authorization: `Bearer ${token}` }, withCredentials: true })
      : peticion.clone({ withCredentials: true });

  return siguiente(conToken(auth.accessToken())).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
        return throwError(() => error);
      }
      return from(auth.refresh()).pipe(
        switchMap((renovado) => {
          if (!renovado) {
            return throwError(() => error);
          }
          return siguiente(conToken(auth.accessToken()));
        }),
      );
    }),
  );
};
