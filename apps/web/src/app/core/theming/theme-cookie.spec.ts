import { describe, expect, it } from 'vitest';

import {
  NOMBRE_COOKIE_TEMA,
  atributoDeTemaParaHtml,
  leerModoDeCookie,
  leerModoDeCookieOpcional,
  serializarCookieDeTema,
} from './theme-cookie';

describe('theme-cookie', () => {
  it('sin cabecera, no hay preferencia (leerModoDeCookieOpcional) y el valor por defecto es oscuro', () => {
    expect(leerModoDeCookieOpcional(null)).toBeNull();
    expect(leerModoDeCookieOpcional(undefined)).toBeNull();
    expect(leerModoDeCookieOpcional('')).toBeNull();
    expect(leerModoDeCookie(null)).toBe('oscuro');
  });

  it('lee la cookie entre otras cookies', () => {
    const cabecera = `otra=1; ${NOMBRE_COOKIE_TEMA}=claro; tercera=x`;
    expect(leerModoDeCookieOpcional(cabecera)).toBe('claro');
    expect(leerModoDeCookie(cabecera)).toBe('claro');
  });

  it('un valor desconocido se trata como oscuro, no como ausencia', () => {
    expect(leerModoDeCookieOpcional(`${NOMBRE_COOKIE_TEMA}=lo-que-sea`)).toBe('oscuro');
  });

  it('serializa con los atributos exigidos', () => {
    const cadena = serializarCookieDeTema('claro');
    expect(cadena).toContain(`${NOMBRE_COOKIE_TEMA}=claro`);
    expect(cadena).toContain('Path=/');
    expect(cadena).toContain('SameSite=Lax');
    expect(cadena).not.toContain('HttpOnly');
  });

  it('el atributo data-theme solo existe para el modo claro', () => {
    expect(atributoDeTemaParaHtml('claro')).toBe('light');
    expect(atributoDeTemaParaHtml('oscuro')).toBeNull();
  });
});
