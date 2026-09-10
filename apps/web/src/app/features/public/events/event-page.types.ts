/**
 * Formas de datos de `GET /public/events/{slug}`, compartidas entre
 * `event-page.ts` y sus secciones extraídas (`sections/`).
 *
 * Refleja `PublicEventDetail` (`apps/api/app/modules/events/schemas.py:312-329`)
 * y los alias `Literal` de ese mismo módulo (líneas 16-19): ningún campo aquí es
 * inventado, cada uno tiene su contraparte real en la API pública.
 */

export type LocationMode = 'in_person' | 'online' | 'hybrid';
export type RegistrationMode = 'free' | 'approval' | 'paid';

export interface PublicParticipant {
  readonly display_name: string;
  readonly role_key: string;
  readonly public_slug: string | null;
}

export interface PublicEventSession {
  readonly id: string;
  readonly session_type: string;
  readonly title: string;
  readonly description: string | null;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly room: string | null;
  /** Sede de la sesión; `null` si el evento no usa sedes o la sesión no tiene. */
  readonly venue_id: string | null;
  readonly video_platform: string | null;
  readonly video_url: string | null;
  readonly materials: readonly { url?: string; label?: string }[];
  readonly participants: readonly PublicParticipant[];
}

export interface PublicSponsor {
  readonly id: string;
  readonly name: string;
  readonly logo_url: string | null;
  readonly website: string | null;
  readonly contribution_type: 'monetaria' | 'en_especie';
  /** Solo con aportación en especie: describe qué se aporta, nunca cuánto
   * vale — el importe monetario nunca se expone en público. */
  readonly contribution_description: string | null;
}

export interface PublicSponsorTier {
  readonly name: string;
  readonly logo_size: 'large' | 'medium' | 'small';
  readonly sponsors: readonly PublicSponsor[];
}

/** Sede del evento, para la vista de programa multisede. */
export interface PublicVenue {
  readonly id: string;
  readonly name: string;
  readonly address: string | null;
  readonly capacity: number | null;
  readonly latitude: number | null;
  readonly longitude: number | null;
}

export interface PublicEventDetail {
  readonly slug: string;
  readonly title: string;
  readonly summary: string | null;
  readonly description: string | null;
  readonly cover_url: string | null;
  readonly timezone: string;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly location_mode: LocationMode;
  readonly location_name: string | null;
  readonly location_address: string | null;
  readonly online_url: string | null;
  readonly capacity: number | null;
  readonly registration_mode: RegistrationMode;
  /** Precio «desde» del tipo de entrada vigente más barato; `null` si el
   * evento es gratis o, siendo de pago, no tiene ningún tipo vigente ahora
   * mismo. */
  readonly price_from_cents: number | null;
  readonly price_currency: string | null;
  /** `true` solo si entre los tipos vigentes hay más de un precio distinto
   * — con un único precio se muestra el importe solo, sin «Desde». */
  readonly price_multiple: boolean;
  /** Plazas realmente reservadas: con `capacity`, da la ocupación de la ficha. */
  readonly reserved_count: number;
  /** Geocodificación de `location_address`; `null` si no hay dirección o falló. */
  readonly latitude: number | null;
  readonly longitude: number | null;
  readonly sessions: readonly PublicEventSession[];
  /** Con 2 o más, el evento tiene programa multisede. */
  readonly venues: readonly PublicVenue[];
  readonly sponsor_tiers: readonly PublicSponsorTier[];
}

/** Claves i18n para `session_type` (`SessionType`, catálogo cerrado real en
 * `apps/api/app/modules/events/schemas.py:18`): a diferencia de `role_key`, este
 * campo sí es un enum cerrado, así que se traduce por clave sin fallback humanizado. */
const CLAVES_TIPO_SESION: Record<string, string> = {
  talk: 'publico.eventos.sesion.tipo.talk',
  break: 'publico.eventos.sesion.tipo.break',
  service: 'publico.eventos.sesion.tipo.service',
  other: 'publico.eventos.sesion.tipo.other',
};

export function claveTipoSesion(sessionType: string): string {
  return CLAVES_TIPO_SESION[sessionType] ?? CLAVES_TIPO_SESION['other'];
}

/** `role_key` (`PublicParticipant.role_key`) es una etiqueta libre por
 * asignación, sin catálogo cerrado en el backend (ver comentario en
 * `apps/api/app/modules/events/models.py:229`: cada organización puede
 * escribir la que necesite). Los valores de ejemplo del propio backend
 * ("speaker", "moderator", "presenter") se traducen; cualquier otro texto se
 * muestra humanizado en vez de crudo. */
const CLAVES_ROL: Record<string, string> = {
  speaker: 'publico.eventos.rol.speaker',
  moderator: 'publico.eventos.rol.moderator',
  presenter: 'publico.eventos.rol.presenter',
};

export function rolLegible(roleKey: string, traducir: (clave: string) => string): string {
  const clave = CLAVES_ROL[roleKey.toLowerCase()];
  if (clave) {
    return traducir(clave);
  }
  return roleKey
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letra) => letra.toUpperCase());
}
