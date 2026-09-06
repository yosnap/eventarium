import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

/** Cuerpo de error de la API, en formato `application/problem+json`. */
export interface ProblemDetail {
  readonly title?: string;
  readonly detail?: string;
  readonly status?: number;
  readonly [clave: string]: unknown;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly problem: ProblemDetail | null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Convierte los errores HTTP en `ApiError` con un mensaje ya legible.
 *
 * La API devuelve `problem+json` con un `detail` redactado para personas; se usa ese
 * texto en lugar de inventar mensajes en el cliente, que se desincronizarían.
 */
export const errorInterceptor: HttpInterceptorFn = (peticion, siguiente) =>
  siguiente(peticion).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse)) {
        return throwError(() => error);
      }
      const problema = (error.error ?? null) as ProblemDetail | null;
      const mensaje =
        problema?.detail ??
        problema?.title ??
        (error.status === 0
          ? 'No se ha podido contactar con el servidor.'
          : 'Se ha producido un error inesperado.');
      return throwError(() => new ApiError(error.status, mensaje, problema));
    }),
  );
