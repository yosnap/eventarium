import { describe, expect, it } from 'vitest';

import { componentesOklchDeHex, hexParaSelector, oklchDeHex } from './oklch';

describe('componentesOklchDeHex', () => {
  it('extrae L/C/H de un hex sin redondear', () => {
    const componentes = componentesOklchDeHex('#22c55e');
    expect(componentes).not.toBeNull();
    expect(componentes!.L).toBeGreaterThan(0);
    expect(componentes!.L).toBeLessThan(1);
    expect(componentes!.C).toBeGreaterThan(0);
    expect(componentes!.H).toBeGreaterThanOrEqual(0);
    expect(componentes!.H).toBeLessThan(360);
  });

  it('el verde de referencia de la plataforma da un matiz cercano a 152.4°', () => {
    // Mismo color de referencia que tokens.css (#00ff87 en su forma sRGB).
    const componentes = componentesOklchDeHex('#00ff87');
    expect(componentes!.H).toBeGreaterThan(145);
    expect(componentes!.H).toBeLessThan(160);
  });

  it('blanco y negro dan croma prácticamente nulo (acromáticos)', () => {
    expect(componentesOklchDeHex('#ffffff')!.C).toBeLessThan(0.001);
    expect(componentesOklchDeHex('#000000')!.C).toBeLessThan(0.001);
  });

  it('devuelve null para un valor que no es hex de 6 dígitos', () => {
    expect(componentesOklchDeHex('rojo')).toBeNull();
    expect(componentesOklchDeHex('#fff')).toBeNull();
  });
});

describe('oklchDeHex (tras el refactor sobre componentesOklchDeHex)', () => {
  it('sigue devolviendo una cadena oklch(...) bien formada', () => {
    const resultado = oklchDeHex('#22c55e');
    expect(resultado).toMatch(/^oklch\(\d+\.\d% \d+\.\d{3} \d+\.\d{2}\)$/);
  });

  it('añade la alfa cuando se pide', () => {
    const resultado = oklchDeHex('#22c55e', '0.1');
    expect(resultado).toContain('/ 0.1)');
  });

  it('devuelve null para un valor no coloreable', () => {
    expect(oklchDeHex('no-es-un-color')).toBeNull();
  });
});

describe('hexParaSelector (consumidor existente de oklchDeHex, no debe cambiar)', () => {
  it('un hex ya en formato #rrggbb se devuelve tal cual, en minúsculas', () => {
    expect(hexParaSelector('#22C55E')).toBe('#22c55e');
  });

  it('un valor oklch se convierte a hex', () => {
    const resultado = hexParaSelector('oklch(87.61% 0.2286 152.37)');
    expect(resultado).toMatch(/^#[0-9a-f]{6}$/);
  });
});
