import { describe, expect, it } from 'vitest';

import { analizarEtiquetas } from './etiquetas';

describe('analizarEtiquetas', () => {
  it('normaliza a minúsculas, quita blancos y repetidas y conserva el orden', () => {
    expect(analizarEtiquetas('  IA , Machine   Learning,ia, Diseño-UX ,').etiquetas).toEqual([
      'ia',
      'machine learning',
      'diseño-ux',
    ]);
  });

  it('un texto vacío no da etiquetas ni error', () => {
    expect(analizarEtiquetas('')).toEqual({ etiquetas: [], error: null });
    expect(analizarEtiquetas(' , ,')).toEqual({ etiquetas: [], error: null });
  });

  it('rechaza las demasiado cortas o largas', () => {
    expect(analizarEtiquetas('a').error).toEqual({ tipo: 'longitud', etiqueta: 'a' });
    expect(analizarEtiquetas('x'.repeat(31)).error?.tipo).toBe('longitud');
  });

  it.each(['#ia', 'ia!', 'ia_ok', '🙂ia', '-ia', 'ia-'])('rechaza los caracteres de «%s»', (t) => {
    expect(analizarEtiquetas(t).error?.tipo).toBe('caracteres');
  });

  it('admite como máximo cinco distintas; repetir no cuenta dos veces', () => {
    expect(analizarEtiquetas('aa,bb,cc,dd,ee').error).toBeNull();
    expect(analizarEtiquetas('aa,bb,cc,dd,ee,ff').error).toEqual({ tipo: 'demasiadas' });
    expect(analizarEtiquetas('aa,aa,aa,aa,aa,aa,bb').etiquetas).toEqual(['aa', 'bb']);
  });
});
