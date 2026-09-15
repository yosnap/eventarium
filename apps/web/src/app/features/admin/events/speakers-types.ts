/**
 * Tipos del panel de ponentes, calcados del payload JSON que devuelve la API
 * (`GET /events/{id}/speakers` y su historial por persona), snake_case tal
 * cual.
 */

export interface SpeakerSession {
  readonly id: string;
  readonly titulo: string;
  readonly starts_at: string | null;
}

/** Claves de la ficha de ponente que faltan por rellenar. */
export interface SpeakerCompletitud {
  readonly porcentaje: number;
  readonly rellenas: number;
  readonly total: number;
  readonly faltantes: readonly string[];
}

export interface SpeakerRow {
  readonly organization_member_id: string;
  readonly user_id: string;
  readonly email: string;
  readonly first_name: string | null;
  readonly last_name: string | null;
  readonly titular: string | null;
  readonly sesiones: readonly SpeakerSession[];
  readonly completitud: SpeakerCompletitud;
  readonly ediciones: number;
  readonly public_slug: string | null;
}

export interface EventSpeakersView {
  readonly items: readonly SpeakerRow[];
  readonly total_sesiones: number;
}

export interface SpeakerHistoryItem {
  readonly evento_titulo: string;
  readonly rol: string | null;
  readonly fecha: string | null;
}

/** Iniciales para el monograma: primera letra de nombre y apellidos, con el
 * correo como último recurso cuando falta todo. */
export function monograma(first: string | null, last: string | null, email: string): string {
  const iniciales = [first?.trim()[0], last?.trim()[0]]
    .filter((letra): letra is string => !!letra)
    .map((letra) => letra.toUpperCase());
  if (iniciales.length > 0) {
    return iniciales.join('');
  }
  return email.slice(0, 2).toUpperCase();
}
