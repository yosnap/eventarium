import { describe, expect, it } from 'vitest';

import { formatearFecha } from './formatear-fecha';
import { formatearPrecio } from './formatear-precio';

const INSTANTE = '2027-01-15T18:30:00Z';

describe('formatearFecha', () => {
  it('formatea en el idioma y la zona indicados', () => {
    const opciones = { dateStyle: 'long', timeZone: 'Europe/Madrid' } as const;
    expect(formatearFecha(INSTANTE, 'es-ES', opciones)).toBe('15 de enero de 2027');
    expect(formatearFecha(INSTANTE, 'en-US', opciones)).toBe('January 15, 2027');
  });

  it('con una zona desconocida formatea igualmente', () => {
    expect(formatearFecha(INSTANTE, 'es-ES', { year: 'numeric', timeZone: 'No/Existe' })).toBe(
      '2027',
    );
  });
});

describe('formatearPrecio', () => {
  it('usa el formato del idioma', () => {
    expect(formatearPrecio(1250, 'EUR', 'es-ES')).toBe('12,50 €');
    expect(formatearPrecio(1250, 'EUR', 'en-US')).toBe('€12.50');
  });
});
