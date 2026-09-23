import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { ThemingService } from '../../core/theming/theming.service';
import { PublicShell } from './public-shell';

describe('PublicShell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ThemingService,
          useValue: {
            branding: signal(null),
            error: signal(null),
            plataforma: signal({
              name: 'Eventarium',
              logo_url: null,
              favicon_url: null,
              social_links: [],
              theme_template_id: null,
              theme: null,
            }),
            nombreDeMarca: signal('Eventarium'),
          },
        },
      ],
    });
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('el pie atribuye la plataforma a Humanitek con su logo enlazando a humanitek.org', async () => {
    const fixture = TestBed.createComponent(PublicShell);
    fixture.detectChanges();
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const enlace = raiz.querySelector<HTMLAnchorElement>('footer a.atribucion');
    expect(enlace?.getAttribute('href')).toBe('https://humanitek.org');
    expect(enlace?.getAttribute('rel')).toContain('noopener');
    expect(enlace?.textContent).toContain(es.publico.landing.pie.parteDe);
    const logo = enlace?.querySelector('img');
    expect(logo?.getAttribute('src')).toBe('assets/humanitek-logo.svg');
    expect(logo?.getAttribute('alt')).toBe(es.publico.landing.pie.humanitek);
    expect(logo?.getAttribute('width')).toBeTruthy();
    expect(logo?.getAttribute('height')).toBeTruthy();
  });

  it.each(['light', 'dark'])('no tiene violaciones de accesibilidad en tema %s', async (tema) => {
    document.documentElement.setAttribute('data-theme', tema);
    const fixture = TestBed.createComponent(PublicShell);
    fixture.detectChanges();
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
