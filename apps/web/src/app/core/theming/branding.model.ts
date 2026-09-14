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
 * documento. Sin dominio por organización (fase 6 del plan de organización sin
 * dominio), es la única identidad que sirve este endpoint: la de un evento
 * concreto viaja en el detalle público de ese evento.
 */
export interface PlatformBranding {
  readonly name: string;
  readonly logo_url: string | null;
  readonly favicon_url: string | null;
  readonly social_links: readonly SocialLink[];
  readonly theme_template_id: string | null;
  readonly theme: PlantillaDeTema | null;
}

/** Respuesta de `GET /api/v1/tenant/branding`. */
export interface Branding {
  readonly platform: PlatformBranding;
}
