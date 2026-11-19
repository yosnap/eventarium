import { describe, expect, it } from 'vitest';

import { pseudoTexto, pseudoTraduccion } from './pseudo-idioma';

describe('pseudo-idioma', () => {
  it('acentúa, alarga y respeta variables y etiquetas', () => {
    const resultado = pseudoTexto('Hola, {{ nombre }} <strong>ya</strong>');
    expect(resultado).toContain('{{ nombre }}');
    expect(resultado).toContain('<strong>');
    expect(resultado).toMatch(/^\[Hölá, \{\{ nombre \}\} <strong>ýá<\/strong>·+\]$/);
    expect(resultado.length).toBeGreaterThan('Hola, {{ nombre }} <strong>ya</strong>'.length * 1.4);
  });

  it('recorre los textos anidados', () => {
    expect(pseudoTraduccion({ a: { b: 'si' } })).toEqual({ a: { b: '[šî·]' } });
  });
});
