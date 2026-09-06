import { Branding } from '../app/core/theming/branding.model';

/** Branding de ejemplo para los tests. */
export function brandingDePrueba(sobrescribir: Partial<Branding> = {}): Branding {
  return {
    organization_id: '01920000-0000-7000-8000-000000000001',
    organization_name: 'Organización de prueba',
    organization_slug: 'prueba',
    template_key: 'classic',
    colors: {
      primary: '#1d4ed8',
      'primary-contrast': '#ffffff',
      surface: '#ffffff',
      'surface-muted': '#f1f5f9',
      text: '#0f172a',
      'text-muted': '#475569',
      border: '#cbd5e1',
    },
    fonts: { sans: 'system-ui, sans-serif', heading: 'system-ui, sans-serif' },
    social_links: [{ kind: 'linkedin', url: 'https://linkedin.com/company/prueba' }],
    organizer_blurb: 'Comunidad de prueba',
    logo_url: null,
    favicon_url: null,
    ...sobrescribir,
  };
}
