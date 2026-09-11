import { PlantillaDeTema } from './theme-template.model';

/** Contrato de `GET /api/v1/tenant/branding`. */
export interface SocialLink {
  readonly kind: string;
  readonly url: string;
}

/**
 * Identidad de la plataforma (Eventarium).
 *
 * Es la marca del **chrome** de la web pública: el header, el pie y el título del
 * documento. Se sirve en cualquier host, tenga o no organización asociada.
 */
export interface PlatformBranding {
  readonly name: string;
  readonly logo_url: string | null;
  readonly favicon_url: string | null;
  readonly social_links: readonly SocialLink[];
  readonly theme_template_id: string | null;
  readonly theme: PlantillaDeTema | null;
}

/**
 * Identidad de la organización del host.
 *
 * `null` cuando el host es el de la plataforma (no pertenece a ninguna
 * organización). Su plantilla de tema se aplica a las **páginas de evento**, no
 * al chrome: la marca global es de Eventarium.
 */
export interface OrganizationBranding {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  /** Plantilla de la página pública: `classic` o `minimal`. No confundir con la
   * plantilla de tema (`theme`): esta decide la composición de la portada, `theme`
   * decide la paleta. */
  readonly template_key: string;
  readonly theme: PlantillaDeTema | null;
  readonly social_links: readonly SocialLink[];
  readonly organizer_blurb: string | null;
  readonly logo_url: string | null;
  readonly favicon_url: string | null;
}

/**
 * Respuesta de `GET /api/v1/tenant/branding`.
 *
 * El bloque `platform` llega siempre; `organization` solo cuando el host
 * resuelve a una organización registrada.
 */
export interface Branding {
  readonly platform: PlatformBranding;
  readonly organization: OrganizationBranding | null;
}
