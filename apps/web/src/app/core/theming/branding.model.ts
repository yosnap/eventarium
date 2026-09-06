/** Contrato de `GET /api/v1/tenant/branding`. */
export interface SocialLink {
  readonly kind: string;
  readonly url: string;
}

export interface Branding {
  readonly organization_id: string;
  readonly organization_name: string;
  readonly organization_slug: string;
  /** Plantilla de la página pública: `classic` o `minimal`. */
  readonly template_key: string;
  readonly colors: Readonly<Record<string, string>>;
  readonly fonts: Readonly<Record<string, string>>;
  readonly social_links: readonly SocialLink[];
  readonly organizer_blurb: string | null;
  readonly logo_url: string | null;
  readonly favicon_url: string | null;
}
