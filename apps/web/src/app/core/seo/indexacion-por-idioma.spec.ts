import { describe, expect, it } from 'vitest';

import { decidirIndexacion } from './indexacion-por-idioma';

describe('decidirIndexacion', () => {
  it('las páginas de la plataforma se ofrecen en todos los idiomas', () => {
    const decision = decidirIndexacion({
      ruta: '/eventos',
      activo: 'en-US',
      contenidoDelOrganizador: false,
    });
    expect(decision.canonica).toBe('/en/eventos');
    expect(decision.alternativas).toEqual([
      { idioma: 'es-ES', ruta: '/eventos' },
      { idioma: 'en-US', ruta: '/en/eventos' },
      { idioma: 'x-default', ruta: '/eventos' },
    ]);
    expect(decision.ogLocale).toBe('en_US');
    expect(decision.ogLocaleAlternativos).toEqual(['es_ES']);
  });

  it('el contenido sin traducir apunta al original, sin alternativas', () => {
    const decision = decidirIndexacion({
      ruta: '/acme/iawic',
      activo: 'en-US',
      contenidoDelOrganizador: true,
    });
    expect(decision.canonica).toBe('/acme/iawic');
    expect(decision.alternativas).toEqual([]);
  });

  it('el original no anuncia idiomas que no están al día', () => {
    const decision = decidirIndexacion({
      ruta: '/acme/iawic',
      activo: 'es-ES',
      contenidoDelOrganizador: true,
    });
    expect(decision.canonica).toBe('/acme/iawic');
    expect(decision.alternativas).toEqual([]);
    expect(decision.ogLocaleAlternativos).toEqual([]);
  });

  it('con la traducción al día se anuncian las dos versiones', () => {
    const decision = decidirIndexacion({
      ruta: '/acme/iawic',
      activo: 'en-US',
      contenidoDelOrganizador: true,
      idiomasAlDia: ['en-US'],
    });
    expect(decision.canonica).toBe('/en/acme/iawic');
    expect(decision.alternativas.map((a) => a.idioma)).toEqual(['es-ES', 'en-US', 'x-default']);
  });

  it('un evento escrito en inglés tiene su original en inglés', () => {
    const decision = decidirIndexacion({
      ruta: '/acme/summit',
      activo: 'es-ES',
      contenidoDelOrganizador: true,
      idiomaOrigen: 'en-US',
    });
    expect(decision.canonica).toBe('/en/acme/summit');
    expect(decision.alternativas).toEqual([]);
  });
});
