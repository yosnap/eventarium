import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MisEventosListadoPage } from './mis-eventos-listado-page';
import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

describe('MisEventosListadoPage', () => {
  function configurar(registrations: Partial<RegistrationsService>, ruta: unknown) {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: RegistrationsService, useValue: registrations },
        { provide: ActivatedRoute, useValue: ruta },
      ],
    }).compileComponents();
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('sin token en la URL muestra el error de enlace no válido', async () => {
    configurar({}, rutaConToken(null));

    const fixture = TestBed.createComponent(MisEventosListadoPage);
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('token válido con inscripciones las lista', async () => {
    const getMyRegistrations = vi.fn().mockResolvedValue([
      {
        event_slug: 'ia-week',
        event_title: 'IA Week',
        starts_at: '2026-10-01T10:00:00Z',
        organization_name: 'Humanitek',
        status: 'confirmed',
      },
    ]);
    configurar({ getMyRegistrations }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(MisEventosListadoPage);
    await fixture.whenStable();

    expect(getMyRegistrations).toHaveBeenCalledWith('token-valido');
    expect(fixture.nativeElement.textContent).toContain('IA Week');
    expect(fixture.nativeElement.textContent).toContain('Humanitek');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('token válido sin inscripciones muestra el mensaje neutro', async () => {
    const getMyRegistrations = vi.fn().mockResolvedValue([]);
    configurar({ getMyRegistrations }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(MisEventosListadoPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain(
      'No hay ninguna inscripción asociada a este enlace.',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('token inválido o caducado muestra el error sin distinguir el motivo', async () => {
    const getMyRegistrations = vi.fn().mockRejectedValue(new Error('422'));
    configurar({ getMyRegistrations }, rutaConToken('token-caducado'));

    const fixture = TestBed.createComponent(MisEventosListadoPage);
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
