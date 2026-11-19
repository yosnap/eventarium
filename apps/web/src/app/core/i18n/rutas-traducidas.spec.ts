import { describe, expect, it } from 'vitest';

import { rutaDeServidor, rutaEn, subrutaDeEvento, traducirRuta } from './rutas-traducidas';

describe('rutas traducidas', () => {
  it('traduce las rutas fijas y las subrutas de un evento', () => {
    expect(rutaEn('en-US', 'acceder')).toBe('login');
    expect(rutaEn('en-US', 'ruta-desconocida')).toBe('ruta-desconocida');
    expect(subrutaDeEvento('en-US', 'sesiones/:sessionId')).toBe('sessions/:sessionId');
    expect(rutaDeServidor('en-US', 'vista-previa/**')).toBe('preview/**');
    expect(rutaDeServidor('en-US', 'mis-eventos/ver')).toBe('my-events/view');
  });

  it('pasa una ruta de un idioma a otro en los dos sentidos', () => {
    expect(traducirRuta('/acme/iawic/programa', 'es-ES', 'en-US')).toBe('/acme/iawic/schedule');
    expect(traducirRuta('/acme/iawic/schedule', 'en-US', 'es-ES')).toBe('/acme/iawic/programa');
    expect(traducirRuta('/acme/iawic/sesiones/42?x=1#a', 'es-ES', 'en-US')).toBe(
      '/acme/iawic/sessions/42?x=1#a',
    );
    expect(traducirRuta('/my-events/view', 'en-US', 'es-ES')).toBe('/mis-eventos/ver');
  });

  it('deja igual lo que no es una ruta fija conocida', () => {
    expect(traducirRuta('/acme', 'es-ES', 'en-US')).toBe('/acme');
    expect(traducirRuta('/acme/programa', 'es-ES', 'en-US')).toBe('/acme/programa');
    expect(traducirRuta('/', 'es-ES', 'en-US')).toBe('/');
  });
});
