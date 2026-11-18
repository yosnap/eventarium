import { describe, expect, it } from 'vitest';

import {
  NOMBRE_COOKIE_IDIOMA,
  idiomaDelPrefijo,
  leerIdiomaDeCookie,
  resolverIdioma,
  ofreceCambioDeIdioma,
  serializarCookieDeIdioma,
  urlEnIdioma,
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

describe('urlEnIdioma', () => {
  it('cambia solo el prefijo de idioma', () => {
    expect(urlEnIdioma('/acme/evento?x=1', 'en-US')).toBe('/en/acme/evento?x=1');
    expect(urlEnIdioma('/en/acme/evento', 'es-ES')).toBe('/acme/evento');
    expect(urlEnIdioma('/en', 'es-ES')).toBe('/');
    expect(urlEnIdioma('/', 'en-US')).toBe('/en');
    expect(urlEnIdioma('/en/acme', 'en-US')).toBe('/en/acme');
  });

  it('nunca devuelve una URL de otro sitio', () => {
    expect(urlEnIdioma('//malo.example/x', 'en-US')).toBe('/en');
    expect(urlEnIdioma('https://malo.example', 'es-ES')).toBe('/');
    expect(urlEnIdioma('/en//malo.example', 'es-ES')).toBe('/');
    expect(urlEnIdioma('/\\malo.example', 'en-US')).toBe('/en');
  });

  it('la portada con parámetros no lleva barra final', () => {
    expect(urlEnIdioma('/?x=1', 'en-US')).toBe('/en?x=1');
  });
});

describe('ofreceCambioDeIdioma', () => {
  it('no en los paneles ni en el consentimiento OAuth, que no existen con prefijo', () => {
    expect(ofreceCambioDeIdioma('/oauth/consentimiento?client_id=x')).toBe(false);
    expect(ofreceCambioDeIdioma('/espacio-de-trabajo')).toBe(false);
    expect(ofreceCambioDeIdioma('/dashboard')).toBe(false);
  });

  it('no en un enlace con token, que podría estar ya gastado', () => {
    expect(ofreceCambioDeIdioma('/verificar-inscripcion?token=abc')).toBe(false);
    expect(ofreceCambioDeIdioma('/en/mis-eventos/ver?token=abc')).toBe(false);
  });

  it('sí en el resto de páginas públicas', () => {
    expect(ofreceCambioDeIdioma('/acme/evento?x=1')).toBe(true);
    expect(ofreceCambioDeIdioma('/en/eventos')).toBe(true);
  });
});
