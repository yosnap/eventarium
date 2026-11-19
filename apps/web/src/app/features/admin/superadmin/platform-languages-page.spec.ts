import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { ThemingService } from '../../../core/theming/theming.service';
import { PlatformLanguagesPage } from './platform-languages-page';

describe('PlatformLanguagesPage', () => {
  it('desactiva el inglés y oculta el selector', async () => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ThemingService, useValue: { load: vi.fn().mockResolvedValue(undefined) } },
      ],
    });
    const fixture = TestBed.createComponent(PlatformLanguagesPage);
    const http = TestBed.inject(HttpTestingController);
    http
      .expectOne('/api/v1/admin/identity')
      .flush({ enabled_locales: ['es-ES', 'en-US'], language_switcher_visible: true });
    await fixture.whenStable();

    const casillas = fixture.nativeElement.querySelectorAll(
      'input[type="checkbox"]',
    ) as NodeListOf<HTMLInputElement>;
    expect(casillas[0].disabled).toBe(true);
    casillas[1].click();
    casillas[1].dispatchEvent(new Event('change'));
    casillas[2].click();
    casillas[2].dispatchEvent(new Event('change'));
    await fixture.whenStable();

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    const guardado = http.expectOne(
      (peticion) => peticion.method === 'PATCH' && peticion.url === '/api/v1/admin/identity',
    );
    expect(guardado.request.body).toEqual({
      enabled_locales: ['es-ES'],
      language_switcher_visible: false,
    });
  });
});
