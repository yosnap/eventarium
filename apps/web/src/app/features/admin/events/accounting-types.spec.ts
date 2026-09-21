import { describe, expect, it } from 'vitest';

import { aCents } from './accounting-types';

describe('aCents', () => {
  it('convierte el formato español con miles y decimales', () => {
    expect(aCents('1.234,56')).toBe(123_456);
  });

  it('convierte el formato con solo coma decimal', () => {
    expect(aCents('1234,56')).toBe(123_456);
  });

  it('convierte el formato con punto decimal', () => {
    expect(aCents('1234.56')).toBe(123_456);
  });

  it('convierte el formato estadounidense con miles y decimales', () => {
    expect(aCents('1,234.56')).toBe(123_456);
  });

  it('no confunde un punto de miles sin decimales con un decimal', () => {
    expect(aCents('2.500')).toBe(250_000);
  });

  it('no confunde una coma de miles sin decimales con un decimal', () => {
    expect(aCents('1,850')).toBe(185_000);
  });

  it('lee como decimal un punto con más de 3 cifras detrás', () => {
    expect(aCents('2.5001')).toBe(250);
  });

  it('devuelve null para texto vacío', () => {
    expect(aCents('')).toBeNull();
    expect(aCents('   ')).toBeNull();
  });

  it('devuelve null para texto no numérico', () => {
    expect(aCents('no es un número')).toBeNull();
  });
});
