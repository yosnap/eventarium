import { describe, expect, it } from 'vitest';

import { applyTokens, brandingToCssVariables, brandingToStyleBlock } from './apply-tokens';
import { brandingDePrueba } from '../../../testing/branding.fixture';

describe('applyTokens', () => {
  it('traduce colores y fuentes a custom properties', () => {
    const variables = brandingToCssVariables(brandingDePrueba());

    expect(variables['--color-primary']).toBe('#1d4ed8');
    expect(variables['--color-text-muted']).toBe('#475569');
    expect(variables['--font-heading']).toBe('system-ui, sans-serif');
  });

  it('descarta valores que podrían inyectar CSS', () => {
    const variables = brandingToCssVariables(
      brandingDePrueba({
        colors: {
          primary: '#000000',
          malicioso: 'red;} body{display:none',
          conUrl: 'url(https://ejemplo.com/x.png)',
        },
      }),
    );

    expect(variables['--color-primary']).toBe('#000000');
    expect(variables['--color-malicioso']).toBeUndefined();
    expect(variables['--color-conUrl']).toBeUndefined();
  });

  it('escribe las variables en el documento', () => {
    applyTokens(brandingDePrueba({ colors: { primary: '#ff0000' } }), document);

    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe('#ff0000');
  });

  it('genera un bloque de estilo para el HTML servido por SSR', () => {
    const bloque = brandingToStyleBlock(brandingDePrueba({ colors: { primary: '#123456' } }));

    expect(bloque).toContain(':root{');
    expect(bloque).toContain('--color-primary:#123456;');
  });
});
