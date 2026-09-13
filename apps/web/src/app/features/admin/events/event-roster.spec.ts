import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { EventRoster } from './event-roster';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const EVENT_ID = 'evt-1';

const MIEMBRO_ORGANIZACION = {
  id: 'om-1',
  first_name: 'Ada',
  last_name: 'Lovelace',
  email: 'ada@example.com',
  role_key: 'speaker',
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function crearYCargar(
  http: HttpTestingController,
  roster: unknown[] = [],
  miembros: unknown[] = [MIEMBRO_ORGANIZACION],
): Promise<ComponentFixture<EventRoster>> {
  const fixture = TestBed.createComponent(EventRoster);
  fixture.componentRef.setInput('eventId', EVENT_ID);
  await avanzar(fixture);
  http.expectOne(`/api/v1/events/${EVENT_ID}/members`).flush(roster);
  http
    .expectOne((p) => p.url === '/api/v1/organizations/me/members')
    .flush({ items: miembros, total: miembros.length, limit: 200, offset: 0 });
  await avanzar(fixture);
  return fixture;
}

describe('EventRoster', () => {
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

  it('sin personas explica el estado vacío, sin violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar(http, []);

    expect(fixture.nativeElement.textContent).toContain('Todavía no has añadido a nadie');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige un correo válido antes de invitar', async () => {
    const fixture = await crearYCargar(http);

    fixture.nativeElement.querySelector('.invitar-ponente').dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http.expectNone((p) => p.url === `/api/v1/events/${EVENT_ID}/invitations`);
    expect(fixture.nativeElement.textContent).toContain('Escribe el correo electrónico');
  });

  it('invitar a un correo sin cuenta avisa que se ha enviado, sin recargar el roster', async () => {
    const fixture = await crearYCargar(http);

    const email = fixture.nativeElement.querySelector('#roster-invitar-email') as HTMLInputElement;
    email.value = 'nuevo-ponente@example.com';
    email.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    fixture.nativeElement.querySelector('.invitar-ponente').dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http
      .expectOne(`/api/v1/events/${EVENT_ID}/invitations`)
      .flush({ status: 'invited', member: null, invitation: {} });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Invitación enviada');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('invitar a un correo con cuenta avisa que se ha añadido y recarga el roster', async () => {
    const fixture = await crearYCargar(http);

    const email = fixture.nativeElement.querySelector('#roster-invitar-email') as HTMLInputElement;
    email.value = 'ya-tiene-cuenta@example.com';
    email.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    fixture.nativeElement.querySelector('.invitar-ponente').dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http
      .expectOne(`/api/v1/events/${EVENT_ID}/invitations`)
      .flush({ status: 'added', member: { id: 'm-nuevo' }, invitation: null });
    await avanzar(fixture);

    http
      .expectOne(`/api/v1/events/${EVENT_ID}/members`)
      .flush([{ ...MIEMBRO_ORGANIZACION, id: 'em-2', organization_member_id: 'om-2' }]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('se ha añadido directamente');
    expect(fixture.nativeElement.textContent).toContain('Ada Lovelace');
  });

  it('no tiene violaciones de accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    try {
      const fixture = await crearYCargar(
        http,
        [{ ...MIEMBRO_ORGANIZACION, id: 'em-1', organization_member_id: 'om-1' }],
        [],
      );
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });
});
