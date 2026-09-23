/** Contratos de `/organizations/me/policies` y `/events/{id}/policies`. */

export type TipoPolitica = 'condiciones' | 'reembolsos' | 'privacidad' | 'otras';

/** Orden de muestra: el mismo que devuelve la API. */
export const TIPOS_DE_POLITICA: readonly TipoPolitica[] = [
  'condiciones',
  'reembolsos',
  'privacidad',
  'otras',
];

export interface VersionDePolitica {
  readonly version_id: string;
  readonly kind: TipoPolitica;
  readonly version: number;
  readonly content: string;
  readonly created_at: string;
}

export interface PoliticaDeOrganizacion {
  readonly kind: TipoPolitica;
  readonly current: VersionDePolitica | null;
  readonly last_version: number | null;
}

export interface PoliticasDeOrganizacion {
  readonly can_edit: boolean;
  readonly items: readonly PoliticaDeOrganizacion[];
}

export type OrigenDePolitica = 'evento' | 'organizacion' | 'ninguno';

export interface PoliticaDeEvento {
  readonly kind: TipoPolitica;
  readonly origin: OrigenDePolitica;
  readonly current: VersionDePolitica | null;
  readonly organization: VersionDePolitica | null;
}

export interface PoliticasDeEvento {
  readonly can_edit: boolean;
  readonly items: readonly PoliticaDeEvento[];
}

/** Tope del servidor (`policies/schemas.py::LIMITE_CARACTERES`). */
export const LIMITE_CARACTERES = 50_000;
