import { DOCUMENT, PLATFORM_ID, REQUEST, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';

import { NOMBRE_COOKIE_TEMA } from './theme-cookie';
import { ThemeModeService } from './theme-mode.service';

function peticionConCookie(cookie: string | null): Request {
  const cabeceras = new Headers();
  if (cookie) {
    cabeceras.set('cookie', cookie);
  }
  return new Request('https://ejemplo.test/', { headers: cabeceras });
}

describe('ThemeModeService', () => {
  afterEach(() => {
    document.cookie = `${NOMBRE_COOKIE_TEMA}=; Max-Age=0`;
    document.documentElement.removeAttribute('data-theme');
  });

  function crear(
    plataforma: 'browser' | 'server' = 'browser',
    peticion: Request | null = null,
  ): ThemeModeService {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: PLATFORM_ID, useValue: plataforma },
        { provide: DOCUMENT, useValue: document },
        { provide: REQUEST, useValue: peticion },
      ],
    });
    return TestBed.inject(ThemeModeService);
  }

  it('sin cookie, el modo por defecto es claro', () => {
    const servicio = crear();
    expect(servicio.modo()).toBe('claro');
    expect(servicio.esClaro()).toBe(true);
  });

  it('respeta la cookie guardada en el navegador', () => {
    document.cookie = `${NOMBRE_COOKIE_TEMA}=oscuro`;
    const servicio = crear();
    expect(servicio.modo()).toBe('oscuro');
  });

  it('en servidor lee la cookie de la petición y no escribe nada', () => {
    const servicio = crear('server', peticionConCookie(`${NOMBRE_COOKIE_TEMA}=oscuro`));
    expect(servicio.modo()).toBe('oscuro');

    servicio.alternar();
    expect(servicio.modo()).toBe('oscuro');
  });

  it('en servidor sin cookie en la petición, devuelve claro', () => {
    const servicio = crear('server', peticionConCookie(null));
    expect(servicio.modo()).toBe('claro');
  });

  it('alternar() cambia el modo, escribe la cookie y pinta data-theme', () => {
    const servicio = crear();
    expect(servicio.modo()).toBe('claro');

    servicio.alternar();

    expect(servicio.modo()).toBe('oscuro');
    expect(servicio.esClaro()).toBe(false);
    expect(document.cookie).toContain(`${NOMBRE_COOKIE_TEMA}=oscuro`);
    expect(document.documentElement.getAttribute('data-theme')).toBeNull();

    servicio.alternar();

    expect(servicio.modo()).toBe('claro');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });
});
