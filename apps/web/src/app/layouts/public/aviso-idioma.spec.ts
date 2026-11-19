import { describe, expect, it } from 'vitest';

import { idiomaPreferido } from './aviso-idioma';

describe('idiomaPreferido', () => {
  it('elige el primer idioma del navegador que la plataforma ofrece', () => {
    expect(idiomaPreferido(['en-GB', 'es-ES'])).toBe('en-US');
    expect(idiomaPreferido(['fr-FR', 'es-MX'])).toBe('es-ES');
    expect(idiomaPreferido(['fr-FR', 'de'])).toBeNull();
    expect(idiomaPreferido([])).toBeNull();
  });
});
