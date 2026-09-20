import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import {
  PARES_CRITICOS,
  comprobarContrasteDePlantilla,
  contrastRatio,
  parseHexColor,
  parseOklchColor,
} from './contrast';

/**
 * Extrae los tokens `--nombre: valor;` de un bloque `{...}` de `tokens.css`. Lee el
 * fichero de disco en vez de duplicar los valores a mano: así un token renombrado o
 * reajustado no puede dejar este test comprobando cifras obsoletas en silencio.
 */
function extraerTokens(cssCompleto: string, selector: RegExp): Record<string, string> {
  const bloque = selector.exec(cssCompleto)?.[1];
  if (!bloque) {
    throw new Error(`No se ha encontrado el bloque ${selector} en tokens.css`);
  }
  const tokens: Record<string, string> = {};
  for (const declaracion of bloque.matchAll(/--([a-z0-9-]+):\s*([^;]+);/gi)) {
    tokens[declaracion[1]] = declaracion[2].trim();
  }
  return tokens;
}

function cargarTokensDeTemas(): { dark: Record<string, string>; light: Record<string, string> } {
  const css = readFileSync('src/styles/tokens.css', 'utf-8');
  return {
    dark: extraerTokens(css, /:root\s*\{([^}]*)\}/),
    light: extraerTokens(css, /\[data-theme=['"]light['"]\]\s*\{([^}]*)\}/),
  };
}

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

  it('interpreta oklch() con la misma tabla de valores conocidos que el backend', () => {
    // Blanco y negro puros: L=100%/0%, C=0. Tolerancia por redondeo de conversión.
    expect(parseOklchColor('oklch(100% 0 0)')).toEqual([255, 255, 255]);
    expect(parseOklchColor('oklch(0% 0 0)')).toEqual([0, 0, 0]);
    // #00ff87, valor de referencia del acento oscuro (ver tokens.css).
    const verde = parseOklchColor('oklch(87.61% 0.2286 152.37)')!;
    expect(verde[0]).toBeLessThanOrEqual(1);
    expect(verde[1]).toBeGreaterThanOrEqual(253);
    expect(verde[2]).toBeCloseTo(135, 0);
    expect(parseOklchColor('no-es-oklch')).toBeNull();
  });

  it('PARES_CRITICOS no está vacío', () => {
    expect(PARES_CRITICOS.length).toBeGreaterThan(0);
  });

  it('un color no parseable es un aviso visible, no un descarte silencioso', () => {
    const avisos = comprobarContrasteDePlantilla(
      { fg: 'rebeccapurple', bg: '#000000', surface: '#000000' },
      'dark',
    );
    expect(avisos.some((a) => a.primero === 'fg' && a.ratio === null)).toBe(true);
  });

  it('avisa cuando un par crítico no llega a AA', () => {
    const avisos = comprobarContrasteDePlantilla(
      { fg: '#cccccc', bg: '#ffffff', surface: '#ffffff' },
      'dark',
    );
    const fgBg = avisos.find((a) => a.primero === 'fg' && a.segundo === 'bg');
    expect(fgBg).toBeDefined();
    expect(fgBg!.ratio).not.toBeNull();
    expect(fgBg!.ratio!).toBeLessThan(4.5);
  });

  describe('tokens del sistema (tokens.css, leídos de disco)', () => {
    const { dark, light } = cargarTokensDeTemas();

    it('los dos modos cumplen AA en todos los pares críticos', () => {
      expect(comprobarContrasteDePlantilla(dark, 'dark')).toEqual([]);
      expect(comprobarContrasteDePlantilla(light, 'light')).toEqual([]);
    });

    it('los tokens esperados existen en el fichero (si no, el test de arriba no comprobaría nada)', () => {
      for (const [primero, segundo] of PARES_CRITICOS) {
        expect(dark[primero], `--${primero} en :root`).toBeDefined();
        expect(dark[segundo], `--${segundo} en :root`).toBeDefined();
        expect(light[primero], `--${primero} en [data-theme="light"]`).toBeDefined();
        expect(light[segundo], `--${segundo} en [data-theme="light"]`).toBeDefined();
      }
    });
  });
});
