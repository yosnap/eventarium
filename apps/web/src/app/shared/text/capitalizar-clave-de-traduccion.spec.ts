import { describe, expect, it } from 'vitest';

import { capitalizarClaveDeTraduccion } from './capitalizar-clave-de-traduccion';

describe('capitalizarClaveDeTraduccion', () => {
  it('capitaliza una sola palabra', () => {
    expect(capitalizarClaveDeTraduccion('talk')).toBe('Talk');
    expect(capitalizarClaveDeTraduccion('monetaria')).toBe('Monetaria');
  });

  it('capitaliza cada parte de una clave snake_case, sin dejar el guion bajo', () => {
    // Regresión: la implementación de `event-sponsors.ts` (`.replace('_', '')`)
    // quitaba el guion bajo pero no ponía en mayúscula la letra siguiente,
    // produciendo «Enespecie» en vez de «EnEspecie» — no coincidía con la
    // clave real `tipoEnEspecie` del JSON de idioma.
    expect(capitalizarClaveDeTraduccion('en_especie')).toBe('EnEspecie');
    expect(capitalizarClaveDeTraduccion('in_person')).toBe('InPerson');
  });
});
