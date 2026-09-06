import { describe, expect, it } from 'vitest';

import { checkBrandingContrast, contrastRatio, parseHexColor } from './contrast';

describe('contraste', () => {
  it('interpreta hex de 3 y de 6 dígitos', () => {
    expect(parseHexColor('#fff')).toEqual([255, 255, 255]);
    expect(parseHexColor('#1d4ed8')).toEqual([29, 78, 216]);
    expect(parseHexColor('no-es-color')).toBeNull();
  });

  it('calcula los extremos conocidos de la escala', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
  });

  it('no avisa cuando la paleta cumple AA', () => {
    const avisos = checkBrandingContrast({
      text: '#0f172a',
      'text-muted': '#475569',
      surface: '#ffffff',
      'surface-muted': '#f1f5f9',
      primary: '#1d4ed8',
      'primary-contrast': '#ffffff',
    });

    expect(avisos).toEqual([]);
  });

  it('avisa cuando el texto no se distingue del fondo', () => {
    const avisos = checkBrandingContrast({ text: '#cccccc', surface: '#ffffff' });

    expect(avisos).toHaveLength(1);
    expect(avisos[0].primero).toBe('text');
    expect(avisos[0].ratio).toBeLessThan(4.5);
  });
});
