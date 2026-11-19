import { DOCUMENT } from '@angular/common';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';

import { Idioma, NOMBRE_COOKIE_IDIOMA } from './idioma';
import { IDIOMA, IdiomaService } from './idioma.service';

interface DocumentoFalso {
  cookie: string;
  location: {
    pathname: string;
    reload: ReturnType<typeof vi.fn>;
    assign: ReturnType<typeof vi.fn>;
  };
}

/** `document` mínimo: la cookie guarda solo el último par escrito, como haría un
 * navegador con una sola cookie; `guardaCookies: false` simula que las bloquea. */
function documentoFalso(
  pathname: string,
  cookieInicial = '',
  guardaCookies = true,
): DocumentoFalso {
  let cookie = cookieInicial;
  return {
    get cookie() {
      return cookie;
    },
    set cookie(valor: string) {
      if (guardaCookies) {
        cookie = valor.split(';')[0];
      }
    },
    location: { pathname, reload: vi.fn(), assign: vi.fn() },
  };
}

function servicio(
  documento: DocumentoFalso,
  activo: Idioma,
  plataforma = 'browser',
): IdiomaService {
  TestBed.configureTestingModule({
    providers: [
      { provide: DOCUMENT, useValue: documento },
      { provide: PLATFORM_ID, useValue: plataforma },
      { provide: IDIOMA, useValue: activo },
    ],
  });
  return TestBed.inject(IdiomaService);
}

describe('IdiomaService.sincronizarConCuenta', () => {
  it('con el mismo idioma no recarga', () => {
    const documento = documentoFalso('/dashboard', `${NOMBRE_COOKIE_IDIOMA}=es-ES`);
    expect(servicio(documento, 'es-ES').sincronizarConCuenta('es-ES')).toBe(false);
    expect(documento.location.reload).not.toHaveBeenCalled();
  });

  it('en un panel con otro idioma guarda la cookie y recarga una vez', () => {
    const documento = documentoFalso('/dashboard/events');
    expect(servicio(documento, 'es-ES').sincronizarConCuenta('en-US')).toBe(true);
    expect(documento.cookie).toBe(`${NOMBRE_COOKIE_IDIOMA}=en-US`);
    expect(documento.location.reload).toHaveBeenCalledTimes(1);
  });

  it('en una página pública solo guarda la cookie', () => {
    const documento = documentoFalso('/acme/evento');
    expect(servicio(documento, 'es-ES').sincronizarConCuenta('en-US')).toBe(false);
    expect(documento.cookie).toBe(`${NOMBRE_COOKIE_IDIOMA}=en-US`);
    expect(documento.location.reload).not.toHaveBeenCalled();
  });

  it('si el navegador no guarda la cookie no recarga, para no entrar en bucle', () => {
    const documento = documentoFalso('/dashboard', '', false);
    expect(servicio(documento, 'es-ES').sincronizarConCuenta('en-US')).toBe(false);
    expect(documento.location.reload).not.toHaveBeenCalled();
  });

  it('en el servidor no hace nada', () => {
    const documento = documentoFalso('/dashboard');
    expect(servicio(documento, 'es-ES', 'server').sincronizarConCuenta('en-US')).toBe(false);
    expect(documento.cookie).toBe('');
  });

  it('ignora idiomas fuera del catálogo', () => {
    const documento = documentoFalso('/dashboard');
    expect(servicio(documento, 'es-ES').sincronizarConCuenta('fr-FR')).toBe(false);
    expect(documento.cookie).toBe('');
  });
});

describe('IdiomaService.recargarSiCambiaElIdioma', () => {
  it('del panel en inglés a una página pública recarga en español', () => {
    const documento = documentoFalso('/', `${NOMBRE_COOKIE_IDIOMA}=en-US`);
    expect(servicio(documento, 'en-US').recargarSiCambiaElIdioma('/')).toBe(true);
    expect(documento.location.reload).toHaveBeenCalledTimes(1);
  });

  it('dentro del mismo idioma no recarga', () => {
    const documento = documentoFalso('/dashboard', `${NOMBRE_COOKIE_IDIOMA}=en-US`);
    expect(servicio(documento, 'en-US').recargarSiCambiaElIdioma('/dashboard/events?x=1')).toBe(
      false,
    );
  });

  it('a otra URL de distinto idioma navega a ella con carga completa', () => {
    const documento = documentoFalso('/acme', `${NOMBRE_COOKIE_IDIOMA}=en-US`);
    expect(servicio(documento, 'es-ES').recargarSiCambiaElIdioma('/dashboard#x')).toBe(true);
    expect(documento.location.assign).toHaveBeenCalledWith('/dashboard#x');
  });
});
