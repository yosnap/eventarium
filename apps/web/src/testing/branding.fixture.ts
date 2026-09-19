import { Branding, PlatformBranding } from '../app/core/theming/branding.model';
import { PlantillaDeTema } from '../app/core/theming/theme-template.model';

/** Plantilla de tema de ejemplo para los tests: valores mínimos, no los reales de `tokens.css`. */
export function plantillaDeTemaDePrueba(
  sobrescribir: Partial<PlantillaDeTema> = {},
): PlantillaDeTema {
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

/** Identidad de plataforma de ejemplo (Eventarium). */
export function plataformaDePrueba(sobrescribir: Partial<PlatformBranding> = {}): PlatformBranding {
  return {
    name: 'Eventarium',
    logo_url: null,
    favicon_url: null,
    social_links: [],
    theme_template_id: null,
    theme: null,
    ...sobrescribir,
  };
}

/** Respuesta pública de branding de ejemplo: solo plataforma, la única
 * identidad que sirve `GET /tenant/branding` sin dominio por organización
 * (fase 6 del plan de organización sin dominio). */
export function brandingDePrueba(
  sobrescribir: { platform?: Partial<PlatformBranding> } = {},
): Branding {
  return { platform: plataformaDePrueba(sobrescribir.platform) };
}
