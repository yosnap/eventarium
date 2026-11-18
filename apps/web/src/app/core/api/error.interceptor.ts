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

/** Prefijo con el que Pydantic envolvía los `ValueError` de los validadores
 * propios antes de que la API marcase cada error con `propio`. Se conserva como
 * respaldo para respuestas de una API anterior. */
const PREFIJO_VALIDADOR_PROPIO = 'Value error, ';

/** Un elemento de `errors[]` en un 422 de validación de la API. */
interface ErrorDeValidacion {
  readonly campo?: unknown;
  readonly mensaje?: unknown;
  /** `true` si viene de un validador propio, con un mensaje para personas. */
  readonly propio?: unknown;
}

/**
 * En un 422 de validación, el `detail` es genérico («La petición no supera la
 * validación»). Si alguno de sus `errors` viene de un validador propio («El fin
 * tiene que ser posterior al inicio»), ese dice qué corregir. Los mensajes
 * genéricos de un campo («Debe tener al menos 1 caracteres») no dicen cuál: esos no.
 */
function mensajeDeValidadorPropio(problema: ProblemDetail | null): string | null {
  const errores = problema?.['errors'];
  if (!Array.isArray(errores)) return null;
  for (const error of errores as readonly (ErrorDeValidacion | null)[]) {
    const mensaje = error?.mensaje;
    if (typeof mensaje !== 'string') continue;
    if (error?.propio === true) return mensaje;
    if (mensaje.startsWith(PREFIJO_VALIDADOR_PROPIO)) {
      return mensaje.slice(PREFIJO_VALIDADOR_PROPIO.length);
    }
  }
  return null;
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
        mensajeDeValidadorPropio(problema) ??
        problema?.detail ??
        problema?.title ??
        (error.status === 0
          ? 'No se ha podido contactar con el servidor.'
          : 'Se ha producido un error inesperado.');
      return throwError(() => new ApiError(error.status, mensaje, problema));
    }),
  );
