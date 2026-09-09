import { describe, expect, it } from 'vitest';
import { contrastRatio } from './contrast';

/**
 * Test bilateral explícito: verifica que el parser de contraste TypeScript
 * produzca exactamente los mismos valores que el backend Python contra la
 * tabla de valores conocidos documentada en el plan y en
 * `apps/api/tests/modules/test_theme_templates.py`.
 *
 * Tolerancia: ±0,01 (redondeados a 2 decimales en ambos lados).
 */
describe('Parser bilateral de contraste (TypeScript vs Python)', () => {
  const valoresConocidos = [
    { a: '#ffffff', b: '#000000', esperado: 21.0, desc: 'Blanco vs negro' },
    { a: '#00ff87', b: '#04140d', esperado: 14.09, desc: 'Verde acento vs gris muy oscuro' },
    { a: 'oklch(94% 0.180 152.4)', b: '#000000', esperado: 16.82, desc: 'OkLCh verde vs negro' },
  ];

  it('reproduce exactamente los valores conocidos que prueba el backend Python', () => {
    const tolerancia = 0.01;
    for (const { a, b, esperado, desc } of valoresConocidos) {
      const ratio = contrastRatio(a, b);
      expect(ratio).not.toBeNull();
      if (ratio !== null) {
        const diferencia = Math.abs(ratio - esperado);
        expect(
          diferencia,
          `${desc}: ${a} vs ${b} devolvió ${ratio.toFixed(4)}, esperado ${esperado} (diff ${diferencia.toFixed(4)})`,
        ).toBeLessThanOrEqual(tolerancia);
      }
    }
  });
});
