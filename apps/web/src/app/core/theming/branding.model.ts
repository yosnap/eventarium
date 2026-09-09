import { PlantillaDeTema } from './theme-template.model';

/** Contrato de `GET /api/v1/tenant/branding`. */
export interface SocialLink {
  readonly kind: string;
  readonly url: string;
}

export interface Branding {
  readonly organization_id: string;
  readonly organization_name: string;
  readonly organization_slug: string;
  /** Plantilla de la página pública: `classic` o `minimal`. No confundir con la
   * plantilla de tema (`theme`): esta decide la composición de la portada, `theme`
   * decide la paleta. */
  readonly template_key: string;
  /**
   * Plantilla de tema ya resuelta por el servidor: la elegida por la organización, o
   * la marcada `is_default` si `theme_template_id` es nulo. `null` solo si por lo que
   * sea no hay ninguna plantilla disponible; el cliente se queda entonces con la base
   * de reserva de `tokens.css` en vez de romper.
   */
  readonly theme: PlantillaDeTema | null;
  readonly social_links: readonly SocialLink[];
  readonly organizer_blurb: string | null;
  readonly logo_url: string | null;
  readonly favicon_url: string | null;
}
