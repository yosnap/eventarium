import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { UpcomingEvents } from './upcoming-events';

const EVENTOS_URL = '/api/v1/public/events';

function eventos() {
  return [
    {
      slug: 'ia-week-2027',
      title: 'Congreso IA Aplicada 2027',
      summary: 'Días y tres salas.',
      starts_at: '2027-03-11T09:00:00Z',
    },
  ];
}

/**
 * `ngOnInit` registra la carga como `PendingTasks`, así que `whenStable()`
 * esperaría a que termine: hay que disparar el ciclo con `detectChanges()`
 * (sin esperar estabilidad todavía) antes de responder la petición simulada.
 */
function montar(): ComponentFixture<UpcomingEvents> {
  const fixture = TestBed.createComponent(UpcomingEvents);
  fixture.detectChanges();
  return fixture;
}

async function trasResponder(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('UpcomingEvents', () => {
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
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lista los eventos publicados con su enlace', async () => {
    const fixture = montar();
    http.expectOne(EVENTOS_URL).flush(eventos());
    await trasResponder(fixture);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Próximos eventos');
    expect(texto).toContain('Congreso IA Aplicada 2027');
    expect(texto).toContain('Días y tres salas.');

    const enlaces = fixture.nativeElement.querySelectorAll(
      '.tarjeta',
    ) as NodeListOf<HTMLAnchorElement>;
    expect(enlaces.length).toBe(1);
    expect(enlaces[0].getAttribute('href')).toBe('/eventos/ia-week-2027');

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('sin eventos, dice que todavía no hay ninguno en vez de desaparecer', async () => {
    const fixture = montar();
    http.expectOne(EVENTOS_URL).flush([]);
    await trasResponder(fixture);

    const texto = fixture.nativeElement.textContent as string;
    // La sección sigue ahí, con su encabezado, y el mensaje va dentro.
    expect(texto).toContain('Próximos eventos');
    expect(texto).toContain('Todavía no hay eventos publicados.');
    expect(fixture.nativeElement.querySelectorAll('.tarjeta').length).toBe(0);

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('mientras carga no muestra el mensaje de lista vacía', async () => {
    const fixture = montar();

    // La petición sigue en vuelo: sin datos todavía, pero tampoco sin cargar.
    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Próximos eventos');
    expect(texto).not.toContain('Todavía no hay eventos publicados.');

    http.expectOne(EVENTOS_URL).flush([]);
    await trasResponder(fixture);
    expect(fixture.nativeElement.textContent).toContain('Todavía no hay eventos publicados.');
  });

  it('el rótulo «Próximamente» ya no se repite encima del encabezado', async () => {
    const fixture = montar();
    http.expectOne(EVENTOS_URL).flush(eventos());
    await trasResponder(fixture);

    // Decía lo mismo que «Próximos eventos», justo encima: se retiró.
    const texto = fixture.nativeElement.textContent as string;
    expect(texto).not.toContain('Próximamente');
    expect(fixture.nativeElement.querySelector('.rotulo-seccion')).toBeNull();
  });

  it('no tiene violaciones de accesibilidad en tema claro sin eventos', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    try {
      const fixture = montar();
      http.expectOne(EVENTOS_URL).flush([]);
      await trasResponder(fixture);

      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });
});
