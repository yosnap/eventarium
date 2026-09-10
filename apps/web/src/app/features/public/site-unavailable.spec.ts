import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import { SiteUnavailable } from './site-unavailable';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';

/**
 * Es la pantalla que se enseña precisamente cuando `ThemingService.load()` ha
 * fallado (`theming.service.ts`): por eso este test deja fuera cualquier
 * provider relacionado con el branding —ni real ni doble— y comprueba que la
 * pantalla sigue legible con los tokens estáticos de `tokens.css`, no con los
 * de una organización.
 */
describe('SiteUnavailable', () => {
  it('se renderiza sin ThemingService y sigue siendo legible y accesible', async () => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });

    const fixture = TestBed.createComponent(SiteUnavailable);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelectorAll('h1').length).toBe(1);
    expect(raiz.textContent).toContain('Sitio no disponible');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });
});
