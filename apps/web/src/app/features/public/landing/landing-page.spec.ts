import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Title } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { LandingPage } from './landing-page';

describe('LandingPage', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
        }),
      ],
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('renderiza el hero con un único h1 y las dos llamadas a la acción', async () => {
    const fixture = TestBed.createComponent(LandingPage);
    fixture.detectChanges();
    await fixture.whenStable();

    const raiz: HTMLElement = fixture.nativeElement;
    expect(raiz.querySelectorAll('h1')).toHaveLength(1);
    expect(raiz.querySelector('h1')?.textContent).toContain(es.publico.landing.hero.titulo);
    const enlaces = Array.from(raiz.querySelectorAll('a[href]')).map((a) => a.getAttribute('href'));
    expect(enlaces).toEqual(['/crear-organizacion', '/eventos']);
    expect(TestBed.inject(Title).getTitle()).toBe(es.publico.landing.seo.titulo);
  });

  it.each(['light', 'dark'])('no tiene violaciones de accesibilidad en tema %s', async (tema) => {
    document.documentElement.setAttribute('data-theme', tema);
    const fixture = TestBed.createComponent(LandingPage);
    fixture.detectChanges();
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
