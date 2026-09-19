import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { componentesOklchDeHex } from './oklch';
import { contrastRatio } from './contrast';
import { CROMA_MAXIMA, colorTieneCromaSuficiente, derivarPaletaDeAcento } from './accent-palette';

const CONTRASTE_MINIMO_AA = 4.5;

interface CasoDeMatiz {
  readonly hex: string;
  readonly h_esperado: number;
  readonly tolerancia_h: number;
  readonly on_accent: { readonly dark: string; readonly light: string };
}

interface CasoAcromatico {
  readonly hex: string;
  readonly debe_rechazarse: boolean;
}

interface FixtureCompartido {
  readonly matices: readonly CasoDeMatiz[];
  readonly acromaticos: readonly CasoAcromatico[];
}

/** Fixture única compartida con `apps/api/tests/modules/test_accent_palette.py`
 * — red de seguridad contra una divergencia futura entre las dos
 * implementaciones de la fórmula (Fase 3 del plan «diseño del evento»).
 *
 * Si `apps/api` no está disponible al lado (p. ej. un job de CI que solo
 * hace checkout de `apps/web`), degrada a una fixture vacía en vez de tumbar
 * toda la suite al importar este fichero — `it.each([])` no ejecuta ningún
 * caso, y el aviso deja constancia en el log (hallazgo de red-team). */
const RUTA_FIXTURE = path.resolve(process.cwd(), '../api/tests/fixtures/casos_paleta_acento.json');
const FIXTURE: FixtureCompartido = (() => {
  try {
    return JSON.parse(readFileSync(RUTA_FIXTURE, 'utf-8')) as FixtureCompartido;
  } catch {
    console.warn(
      `[accent-palette.spec] fixture compartida no encontrada en ${RUTA_FIXTURE}; ` +
        'se omiten los casos del fixture compartido con el backend.',
    );
    return { matices: [], acromaticos: [] };
  }
})();

const MATICES_DE_PRUEBA: readonly string[] = FIXTURE.matices.map((caso) => caso.hex);
const COLORES_ACROMATICOS: readonly string[] = FIXTURE.acromaticos.map((caso) => caso.hex);

describe('derivarPaletaDeAcento', () => {
  it.each(MATICES_DE_PRUEBA)('%s: on-accent cumple AA contra accent y accent-hi', (hex) => {
    const paleta = derivarPaletaDeAcento(hex);
    expect(paleta).not.toBeNull();
    for (const modo of ['dark', 'light'] as const) {
      const valores = paleta![modo];
      const ratioAccent = contrastRatio(valores['on-accent'], valores['accent']);
      const ratioAccentHi = contrastRatio(valores['on-accent'], valores['accent-hi']);
      expect(ratioAccent).not.toBeNull();
      expect(ratioAccentHi).not.toBeNull();
      expect(ratioAccent!).toBeGreaterThanOrEqual(CONTRASTE_MINIMO_AA);
      expect(ratioAccentHi!).toBeGreaterThanOrEqual(CONTRASTE_MINIMO_AA);
    }
  });

  it('clampa el croma a CROMA_MAXIMA', () => {
    const paleta = derivarPaletaDeAcento('#00ff00')!;
    const croma = parseFloat(paleta.dark['accent'].split(' ')[1]);
    expect(croma).toBeLessThanOrEqual(CROMA_MAXIMA + 1e-9);
  });

  it('conserva el matiz de entrada', () => {
    const paleta = derivarPaletaDeAcento('#22c55e')!;
    // H es el último componente antes del paréntesis de cierre.
    const tono = parseFloat(paleta.dark['accent'].split(' ')[2].replace(')', ''));
    expect(tono).toBeGreaterThan(0);
    expect(tono).toBeLessThan(360);
  });

  it.each(FIXTURE.matices)('$hex: hue dentro de la tolerancia del fixture compartido', (caso) => {
    const componentes = componentesOklchDeHex(caso.hex);
    expect(componentes).not.toBeNull();
    expect(Math.abs(componentes!.H - caso.h_esperado)).toBeLessThan(caso.tolerancia_h);
  });

  it.each(FIXTURE.matices)('$hex: on-accent exacto según el fixture compartido', (caso) => {
    const paleta = derivarPaletaDeAcento(caso.hex)!;
    expect(paleta.dark['on-accent']).toBe(caso.on_accent.dark);
    expect(paleta.light['on-accent']).toBe(caso.on_accent.light);
  });

  it.each(COLORES_ACROMATICOS)('%s: rechazado por croma insuficiente', (hex) => {
    expect(colorTieneCromaSuficiente(hex)).toBe(false);
    expect(derivarPaletaDeAcento(hex)).toBeNull();
  });

  it('un color con croma suficiente pasa el chequeo previo', () => {
    expect(colorTieneCromaSuficiente('#22c55e')).toBe(true);
  });

  it('devuelve null para un hex inválido', () => {
    expect(derivarPaletaDeAcento('no-es-un-color')).toBeNull();
  });
});
