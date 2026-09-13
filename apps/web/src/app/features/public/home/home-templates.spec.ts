import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, type Type } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { ThemingService } from '../../../core/theming/theming.service';
import { themingDePrueba } from '../../../../testing/theming.fixture';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { ClassicTemplate } from './classic-template';
import { MinimalTemplate } from './minimal-template';

const EVENTOS_URL = '/api/v1/public/events';

/**
 * Las dos plantillas de portada comparten la misma decisión: el rótulo y el
 * aviso de «próximamente» que iban en su hero se retiraron, porque decían que
 * la edición estaba por llegar mientras la sección de debajo ya listaba los
 * eventos publicados. Se comprueba en las dos, no en una.
 */
function describirPlantilla(nombre: string, Plantilla: Type<unknown>): void {
  describe(`plantilla de portada «${nombre}»`, () => {
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
          provideRouter([]),
          { provide: ThemingService, useValue: themingDePrueba() },
        ],
      });
      http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
      http.verify();
    });

    /** La carga de eventos va como `PendingTasks`: se responde antes de esperar. */
    async function montarCon(eventos: unknown[]): Promise<ComponentFixture<unknown>> {
      const fixture = TestBed.createComponent(Plantilla);
      fixture.detectChanges();
      http.expectOne(EVENTOS_URL).flush(eventos);
      await fixture.whenStable();
      fixture.detectChanges();
      return fixture;
    }

    it('no anuncia «próximamente» sobre un listado de eventos publicados', async () => {
      const fixture = await montarCon([
        {
          slug: 'ia-week-2027',
          title: 'Congreso IA Aplicada 2027',
          summary: null,
          starts_at: '2027-03-11T09:00:00Z',
        },
      ]);

      const texto = fixture.nativeElement.textContent as string;
      expect(texto).not.toContain('Próximamente');
      expect(texto).not.toContain('Estamos preparando la próxima edición');
      // Y sin embargo sí muestra el evento, que es lo que contradecía al aviso.
      expect(texto).toContain('Congreso IA Aplicada 2027');
    });

    it('muestra la marca del organizador y no tiene violaciones de accesibilidad', async () => {
      const fixture = await montarCon([]);

      expect(fixture.nativeElement.querySelector('h1')?.textContent?.trim()).toBeTruthy();
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });
  });
}

describirPlantilla('classic', ClassicTemplate);
describirPlantilla('minimal', MinimalTemplate);
