import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { EventScope } from './event-scope';
import { EventShell } from './event-shell';

function montar(opciones: {
  readonly nombreEvento?: string | null;
  readonly registrationMode?: 'free' | 'approval' | 'paid' | null;
}) {
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
      {
        provide: EventScope,
        useValue: {
          nombreEvento: signal(opciones.nombreEvento ?? null),
          registrationMode: signal(opciones.registrationMode ?? null),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(EventShell);
  fixture.componentRef.setInput('eventId', 'e1');
  return fixture;
}

describe('EventShell', () => {
  it('pinta el nombre del evento en el título', async () => {
    const fixture = montar({ nombreEvento: 'IA Week in Cascais 2026' });
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('h1')?.textContent).toContain('IA Week in Cascais 2026');
  });

  it('mientras el nombre carga, el título muestra el texto de carga', async () => {
    const fixture = montar({ nombreEvento: null });
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('h1')?.textContent).toContain('Cargando evento…');
  });

  it('lleva un enlace de vuelta a la lista de eventos', async () => {
    const fixture = montar({});
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const volver = raiz.querySelector('a[href="/dashboard/events"]');
    expect(volver).toBeTruthy();
    expect(volver?.getAttribute('aria-label')).toBeTruthy();
  });

  it('sin pagos: no ofrece las pestañas de entradas, descuentos ni pagos', async () => {
    const fixture = montar({ registrationMode: 'free' });
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const enlaces = Array.from(raiz.querySelectorAll('nav.pestanas a')).map((a) =>
      a.getAttribute('href'),
    );
    expect(enlaces).toContain('/dashboard/events/e1');
    expect(enlaces).toContain('/dashboard/events/e1/editar');
    expect(enlaces).toContain('/dashboard/events/e1/agenda');
    expect(enlaces).toContain('/dashboard/events/e1/contabilidad');
    expect(enlaces).not.toContain('/dashboard/events/e1/entradas');
    expect(enlaces).not.toContain('/dashboard/events/e1/payments');
  });

  it('con pagos: añade las pestañas de entradas, descuentos y pagos', async () => {
    const fixture = montar({ registrationMode: 'paid' });
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const enlaces = Array.from(raiz.querySelectorAll('nav.pestanas a')).map((a) =>
      a.getAttribute('href'),
    );
    expect(enlaces).toContain('/dashboard/events/e1/entradas');
    expect(enlaces).toContain('/dashboard/events/e1/descuentos');
    expect(enlaces).toContain('/dashboard/events/e1/payments');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = montar({ nombreEvento: 'IA Week' });
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
