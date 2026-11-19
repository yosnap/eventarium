import type { OrganizacionPublica } from '../../../shared/ui/migas-de-evento';
import type { PlantillaDeTema } from '../../../core/theming/theme-template.model';
import type { IdiomasDeLaRespuesta } from '../../../core/seo/indexacion-por-idioma';

/**
 * Formas de datos de `GET /public/organizations/{org}/events/{slug}`, compartidas entre
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
  /** Identificador opaco de la persona: el mismo en `speakers` y en la agenda. */
  readonly ref: string;
}

export interface PublicEventSession {
  readonly id: string;
  readonly session_type: string;
  readonly type?: TipoDeSesionPublico;
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

/** Un sitio que el organizador señala cerca del evento. */
export interface PublicNearbyPlace {
  readonly kind: 'hotel' | 'restaurant' | 'bar' | 'parking' | 'transport' | 'pharmacy' | 'other';
  readonly custom_kind: string | null;
  readonly name: string;
  readonly address: string | null;
  readonly phone: string | null;
  readonly website: string | null;
  readonly notes: string | null;
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

export interface PublicEventDetail extends IdiomasDeLaRespuesta {
  readonly nearby_places?: readonly PublicNearbyPlace[];
  /** `hidden` = «solo con enlace»: se marca `noindex`. */
  readonly visibility?: 'public' | 'hidden' | 'private';
  readonly organization: OrganizacionPublica;
  /** Categoría activa del catálogo; `null` si no tiene o está desactivada. */
  readonly category?: { readonly slug: string; readonly name: string } | null;
  readonly tags?: readonly string[];
  /** Texto de cada etiqueta en el idioma de la página (solo las que cambian). */
  readonly tag_labels?: Readonly<Record<string, string>>;
  /** Plantilla propia del evento; `null` es que hereda la de su organización. */
  readonly theme?: PlantillaDeTema | null;
  readonly slug: string;
  /** El evento está cancelado: la ficha sigue visible con el aviso. */
  readonly cancelled?: boolean;
  readonly cancellation_reason?: string | null;
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
  /** Venta de entradas de un evento de pago: `open`, `upcoming` (abre en
   * `ticket_sales_opens_at`) o `closed`; `null` si no es de pago. */
  readonly ticket_sales?: 'open' | 'upcoming' | 'closed' | null;
  readonly ticket_sales_opens_at?: string | null;
  /** Plazas realmente reservadas: con `capacity`, da la ocupación de la ficha. */
  readonly reserved_count: number;
  /** Geocodificación de `location_address`; `null` si no hay dirección o falló. */
  readonly latitude: number | null;
  readonly longitude: number | null;
  readonly sessions: readonly PublicEventSession[];
  /** Ponentes enlazados al evento, tengan o no sesión. */
  readonly speakers?: readonly PublicParticipant[];
  /** Con 2 o más, el evento tiene programa multisede. */
  readonly venues: readonly PublicVenue[];
  readonly sponsor_tiers: readonly PublicSponsorTier[];
}

/** El tipo de una sesión, del catálogo de su organización (`SessionTypeRef`). */
export interface TipoDeSesionPublico {
  readonly id: string;
  readonly name: string;
  readonly color: string;
  readonly is_break: boolean;
}

/** Respaldo para una respuesta sin `type` (anterior a los tipos por
 * organización): el texto heredado traducido por su clave base. */
const CLAVES_TIPO_SESION: Record<string, string> = {
  talk: 'publico.eventos.sesion.tipo.talk',
  workshop: 'publico.eventos.sesion.tipo.workshop',
  break: 'publico.eventos.sesion.tipo.break',
  service: 'publico.eventos.sesion.tipo.service',
  other: 'publico.eventos.sesion.tipo.other',
};

/** Nombre del tipo de una sesión: el que le dio la organización. */
export function nombreTipoSesion(
  sesion: { readonly type?: TipoDeSesionPublico; readonly session_type: string },
  traducir: (clave: string) => string,
): string {
  return (
    sesion.type?.name ??
    traducir(CLAVES_TIPO_SESION[sesion.session_type] ?? CLAVES_TIPO_SESION['other']!)
  );
}

/** Pausa (descanso, comida…): la marca el tipo; sin él, el texto heredado. */
export function esPausa(sesion: {
  readonly type?: TipoDeSesionPublico;
  readonly session_type: string;
}): boolean {
  return sesion.type?.is_break ?? ['break', 'service'].includes(sesion.session_type);
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
