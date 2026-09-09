import { DOCUMENT, PLATFORM_ID, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import { ThemeToggle } from './theme-toggle';
import { NOMBRE_COOKIE_TEMA } from '../../core/theming/theme-cookie';
import { ThemeModeService } from '../../core/theming/theme-mode.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';

describe('ThemeToggle', () => {
  afterEach(() => {
    document.cookie = `${NOMBRE_COOKIE_TEMA}=; Max-Age=0`;
    document.documentElement.removeAttribute('data-theme');
  });

  async function montar(): Promise<ComponentFixture<ThemeToggle>> {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: DOCUMENT, useValue: document },
      ],
    });
    const fixture = TestBed.createComponent(ThemeToggle);
    await fixture.whenStable();
    return fixture;
  }

  it('es un botón real con aria-pressed y nombre accesible, sin violaciones de axe', async () => {
    const fixture = await montar();
    const boton = fixture.nativeElement.querySelector('button') as HTMLButtonElement;

    expect(boton).toBeTruthy();
    expect(boton.getAttribute('aria-pressed')).toBe('false');
    expect(boton.getAttribute('aria-label')?.length).toBeGreaterThan(0);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('al pulsar, alterna el modo sin remontar el botón', async () => {
    const fixture = await montar();
    const boton = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    const referenciaOriginal = boton;

    boton.click();
    await fixture.whenStable();

    const botonTrasClick = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(botonTrasClick).toBe(referenciaOriginal);
    expect(botonTrasClick.getAttribute('aria-pressed')).toBe('true');

    const servicio = TestBed.inject(ThemeModeService);
    expect(servicio.modo()).toBe('claro');
  });
});
