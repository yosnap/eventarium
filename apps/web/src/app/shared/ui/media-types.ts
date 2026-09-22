/** Tipos y helpers de la biblioteca de medios, compartidos entre
 * `media-fields.ts` y `media-edit-dialog.ts`.
 *
 * En fichero aparte a propósito: `media-edit-dialog.ts` importaba estos
 * símbolos directamente de `media-fields.ts`, y `media-fields.ts` importa
 * `MediaEditDialog` — un ciclo de módulos que rompía la metadata de
 * `@Component` en tiempo de ejecución (`NG0919`) en cualquier consumidor
 * lejano de `MediaFields` (p. ej. `event-details.ts`), no solo en los dos
 * ficheros implicados (hallazgo al ejecutar la suite completa, no detectado
 * por `tsc`/ESLint ni por los specs de los dos ficheros por separado). */

/** Catálogo cerrado — igual que `KIND_A_PERMISO` en el backend
 * (`app/modules/media/service.py`). `platform` no lleva `kind` en sus
 * peticiones: es un único contexto sin ese campo. */
export type MediaKind = 'branding' | 'events' | 'sponsors' | 'platform';

export interface MediaItem {
  readonly id: string;
  readonly url: string;
  readonly filename: string;
  readonly alt: string | null;
  readonly folder_id: string | null;
}

export interface MediaFolder {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
}

export function baseDeMedia(kind: MediaKind): string {
  return kind === 'platform' ? '/admin/platform/media' : '/organizations/me/media';
}
