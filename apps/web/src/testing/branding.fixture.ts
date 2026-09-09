import { Branding } from '../app/core/theming/branding.model';
import { PlantillaDeTema } from '../app/core/theming/theme-template.model';

/** Plantilla de tema de ejemplo para los tests: valores mínimos, no los reales de `tokens.css`. */
export function plantillaDeTemaDePrueba(sobrescribir: Partial<PlantillaDeTema> = {}): PlantillaDeTema {
  return {
    id: '01920000-0000-7000-8000-0000000000f1',
    key: 'oscuro',
    name: 'Oscuro',
    tokens: {
      dark: {
        bg: '#080808',
        surface: '#141414',
        'surface-2': '#0f0f0f',
        fg: '#f0f0f0',
        muted: '#999999',
        accent: '#00ff87',
        'on-accent': '#080808',
        danger: '#ff4d4f',
        warn: '#ff4f00',
      },
      light: {
        bg: '#f5f5f5',
        surface: '#ffffff',
        'surface-2': '#f2f2f2',
        fg: '#0b0b0b',
        muted: '#4d4d4d',
        accent: '#006b26',
        'on-accent': '#ffffff',
        danger: '#a92200',
        warn: '#ab2200',
      },
    },
    ...sobrescribir,
  };
}

/** Branding de ejemplo para los tests. */
export function brandingDePrueba(sobrescribir: Partial<Branding> = {}): Branding {
  return {
    organization_id: '01920000-0000-7000-8000-000000000001',
    organization_name: 'Organización de prueba',
    organization_slug: 'prueba',
    template_key: 'classic',
    theme: plantillaDeTemaDePrueba(),
    social_links: [{ kind: 'linkedin', url: 'https://linkedin.com/company/prueba' }],
    organizer_blurb: 'Comunidad de prueba',
    logo_url: null,
    favicon_url: null,
    ...sobrescribir,
  };
}
