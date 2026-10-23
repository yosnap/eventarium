import { describe, expect, it } from 'vitest';

import { localeDeCuenta } from './locale-de-cuenta';

/**
 * Fase 3 (plan `261019-1343-parametro-idioma-registro-invitacion`): el helper
 * nunca debe enviar al backend un código de idioma fuera del catálogo
 * `'es-ES' | 'en-US'` — un idioma de interfaz futuro que el backend no
 * conozca (p. ej. `'en'` en vez de `'en-US'`) no debe convertir el parámetro
 * opcional `locale` en un 422 que bloquee el alta de cuentas.
 */
describe('localeDeCuenta', () => {
  it('devuelve el idioma activo cuando está en el catálogo (es-ES)', () => {
    expect(localeDeCuenta('es-ES')).toBe('es-ES');
  });

  it('devuelve el idioma activo cuando está en el catálogo (en-US)', () => {
    expect(localeDeCuenta('en-US')).toBe('en-US');
  });

  it('cae a es-ES para un código fuera de catálogo, vacío o ausente', () => {
    expect(localeDeCuenta('en')).toBe('es-ES');
    expect(localeDeCuenta('')).toBe('es-ES');
    expect(localeDeCuenta(undefined)).toBe('es-ES');
    expect(localeDeCuenta(null)).toBe('es-ES');
  });
});
