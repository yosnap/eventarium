import { describe, expect, it } from 'vitest';

import {
  NOMBRE_COOKIE_IDIOMA,
  idiomaDelPrefijo,
  leerIdiomaDeCookie,
  resolverIdioma,
  serializarCookieDeIdioma,
} from './idioma';

const COOKIE_EN = `otra=1; ${NOMBRE_COOKIE_IDIOMA}=en-US`;

describe('idiomaDelPrefijo', () => {
  it('reconoce el prefijo de un idioma del catálogo', () => {
    expect(idiomaDelPrefijo('/en')).toBe('en-US');
    expect(idiomaDelPrefijo('/en/acme/evento')).toBe('en-US');
    expect(idiomaDelPrefijo('/en?x=1')).toBe('en-US');
  });

  it('no confunde una organización ni el idioma por defecto con un prefijo', () => {
    expect(idiomaDelPrefijo('/')).toBeNull();
    expect(idiomaDelPrefijo('/acme/evento')).toBeNull();
    expect(idiomaDelPrefijo('/english')).toBeNull();
    expect(idiomaDelPrefijo('/es/acme')).toBeNull();
  });
});

describe('leerIdiomaDeCookie', () => {
  it('lee la cookie y descarta valores fuera del catálogo', () => {
    expect(leerIdiomaDeCookie(COOKIE_EN)).toBe('en-US');
    expect(leerIdiomaDeCookie(`${NOMBRE_COOKIE_IDIOMA}=../../etc`)).toBeNull();
    expect(leerIdiomaDeCookie(null)).toBeNull();
  });

  it('la cookie que escribe es la que lee', () => {
    const cookie = serializarCookieDeIdioma('en-US').split(';')[0];
    expect(leerIdiomaDeCookie(cookie)).toBe('en-US');
  });
});

describe('resolverIdioma', () => {
  it('el prefijo de la URL manda', () => {
    expect(resolverIdioma('/en/acme', null)).toBe('en-US');
  });

  it('los paneles siguen la cookie del idioma de la cuenta', () => {
    expect(resolverIdioma('/dashboard/events', COOKIE_EN)).toBe('en-US');
    expect(resolverIdioma('/admin', COOKIE_EN)).toBe('en-US');
    expect(resolverIdioma('/dashboard', null)).toBe('es-ES');
  });

  it('una página pública sin prefijo es siempre del idioma por defecto', () => {
    expect(resolverIdioma('/acme/evento', COOKIE_EN)).toBe('es-ES');
    expect(resolverIdioma('/', COOKIE_EN)).toBe('es-ES');
  });
});
