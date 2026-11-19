import { describe, expect, it } from 'vitest';

import { fechaRelativa } from './fecha-relativa';

const AHORA = new Date('2026-09-15T12:00:00Z');

describe('fechaRelativa', () => {
  it('menos de un minuto es «ahora»', () => {
    expect(fechaRelativa('2026-09-15T11:59:30Z', 'es-ES', AHORA)).toBe('ahora');
  });

  it('minutos, horas y días con el formato corto de la referencia', () => {
    expect(fechaRelativa('2026-09-15T11:30:00Z', 'es-ES', AHORA)).toBe('hace 30 min');
    expect(fechaRelativa('2026-09-15T10:00:00Z', 'es-ES', AHORA)).toBe('hace 2 h');
    expect(fechaRelativa('2026-09-13T12:00:00Z', 'es-ES', AHORA)).toBe('hace 2 días');
  });

  it('meses y años con singular y plural', () => {
    expect(fechaRelativa('2026-08-10T12:00:00Z', 'es-ES', AHORA)).toBe('hace 1 mes');
    expect(fechaRelativa('2026-07-10T12:00:00Z', 'es-ES', AHORA)).toBe('hace 2 meses');
    expect(fechaRelativa('2025-09-15T12:00:00Z', 'es-ES', AHORA)).toBe('hace 1 año');
    expect(fechaRelativa('2024-03-15T12:00:00Z', 'es-ES', AHORA)).toBe('hace 2 años');
  });

  it('un ISO inválido devuelve cadena vacía, no NaN', () => {
    expect(fechaRelativa('no-es-una-fecha', 'es-ES', AHORA)).toBe('');
  });

  it('las fechas futuras (relojes descuadrados) también son «ahora»', () => {
    expect(fechaRelativa('2026-09-15T12:05:00Z', 'es-ES', AHORA)).toBe('ahora');
  });

  it('en el idioma de la página', () => {
    expect(fechaRelativa('2026-09-15T11:59:30Z', 'en-US', AHORA)).toBe('now');
    expect(fechaRelativa('2026-09-13T12:00:00Z', 'en-US', AHORA)).toBe('2 days ago');
    expect(fechaRelativa('2026-07-10T12:00:00Z', 'en-US', AHORA)).toBe('2 months ago');
  });
});
