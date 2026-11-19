import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { ThemingService } from '../../core/theming/theming.service';
import { PestanasDeIdioma } from './pestanas-de-idioma';

const URL = '/api/v1/translations/event/e1?locale=en-US';

const vaciar = () => new Promise((resolver) => setTimeout(resolver));

describe('PestanasDeIdioma', () => {
  let http: HttpTestingController;

  beforeEach(() => {
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
        // Plataforma con dos idiomas activos: sin ella las pestañas no preguntan.
        {
          provide: ThemingService,
          useValue: { plataforma: signal({ enabled_locales: ['es-ES', 'en-US'] }) },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  async function crear(locales: string[]) {
    const fixture = TestBed.createComponent(PestanasDeIdioma);
    fixture.componentRef.setInput('tipo', 'event');
    fixture.componentRef.setInput('entityId', 'e1');
    fixture.detectChanges();
    http.expectOne(URL).flush({ locale: 'en-US', source_locale: 'es-ES', locales, items: [] });
    await vaciar();
    fixture.detectChanges();
    return fixture;
  }

  it('con un solo idioma no muestra pestañas', async () => {
    const fixture = await crear(['es-ES']);
    expect(fixture.nativeElement.querySelectorAll('[role="tab"]').length).toBe(0);
  });

  it('con dos idiomas abre el editor del otro al pulsar su pestaña', async () => {
    const fixture = await crear(['es-ES', 'en-US']);
    const pestanas = fixture.nativeElement.querySelectorAll('[role="tab"]');
    expect(pestanas.length).toBe(2);
    expect(pestanas[0].textContent).toContain('Español');

    (pestanas[1] as HTMLButtonElement).click();
    fixture.detectChanges();
    http.expectOne(URL).flush({
      locale: 'en-US',
      source_locale: 'es-ES',
      locales: ['es-ES', 'en-US'],
      items: [
        {
          entity_type: 'event',
          entity_id: 'e1',
          field: 'title',
          original: 'Jornada',
          value: null,
          origin: null,
          status: 'pendiente',
        },
      ],
    });
    await vaciar();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Título');
    expect(fixture.nativeElement.textContent).toContain('Sin traducir');
  });

  it('sin entidad guardada no pide nada ni muestra pestañas', () => {
    const fixture = TestBed.createComponent(PestanasDeIdioma);
    fixture.componentRef.setInput('tipo', 'event');
    fixture.detectChanges();
    http.expectNone(URL);
    expect(fixture.nativeElement.querySelectorAll('[role="tab"]').length).toBe(0);
  });
});
