import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { InvitationsPanel } from './invitations-panel';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const ROLES = [{ id: 'r1', key: 'organizer', name: 'Organizador' }];

const INVITACION = {
  id: 'i1',
  email: 'pendiente@example.com',
  role_id: 'r1',
  role_key: 'organizer',
  estado: 'pendiente',
  expires_at: '2099-01-01T00:00:00Z',
  created_at: '2026-01-01T00:00:00Z',
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function crearYCargar(
  http: HttpTestingController,
  invitaciones: unknown[] = [],
): Promise<ComponentFixture<InvitationsPanel>> {
  const fixture = TestBed.createComponent(InvitationsPanel);
  await avanzar(fixture);
  http.expectOne('/api/v1/organizations/me/invitations').flush(invitaciones);
  http.expectOne('/api/v1/roles').flush(ROLES);
  await avanzar(fixture);
  // `cargar()` espera `Promise.all(...)`: un segundo ciclo de estabilidad para
  // que el `finally` que apaga `cargando` llegue al DOM.
  await avanzar(fixture);
  return fixture;
}

describe('InvitationsPanel', () => {
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
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  afterEach(() => {
    http.verify();
    vi.restoreAllMocks();
  });

  it('sin invitaciones explica qué es y cómo invitar, sin violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar(http, []);

    expect(fixture.nativeElement.textContent).toContain('No hay invitaciones pendientes');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('lista una invitación con su estado legible por texto', async () => {
    const fixture = await crearYCargar(http, [INVITACION]);

    expect(fixture.nativeElement.textContent).toContain('pendiente@example.com');
    const chip = fixture.nativeElement.querySelector('app-chip');
    expect(chip?.textContent?.trim()).toBe('Pendiente');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige email y rol antes de invitar', async () => {
    const fixture = await crearYCargar(http, []);

    fixture.nativeElement.querySelector('.formulario-invitar').dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('Escribe el correo electrónico');
    expect(fixture.nativeElement.textContent).toContain('Elige un rol');
  });

  it('invitar recarga la lista y muestra el mensaje según la rama del servicio', async () => {
    const fixture = await crearYCargar(http, []);

    const email = fixture.nativeElement.querySelector('#invitacion-email') as HTMLInputElement;
    email.value = 'nueva@example.com';
    email.dispatchEvent(new Event('input'));
    const select = fixture.nativeElement.querySelector('#invitacion-rol') as HTMLSelectElement;
    select.value = 'r1';
    select.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    fixture.nativeElement.querySelector('.formulario-invitar').dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http
      .expectOne('/api/v1/organizations/me/invitations')
      .flush({ status: 'invited', member: null, invitation: INVITACION });
    await avanzar(fixture);

    http.expectOne('/api/v1/organizations/me/invitations').flush([INVITACION]);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Invitación enviada');
  });

  it('revocar pide confirmación y, si se acepta, llama al endpoint y recarga', async () => {
    const fixture = await crearYCargar(http, [INVITACION]);

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as HTMLButtonElement[];
    const revocar = botones.find((b) => b.textContent?.includes('Revocar'));
    revocar?.click();
    await avanzar(fixture);

    expect(window.confirm).toHaveBeenCalled();
    http.expectOne('/api/v1/organizations/me/invitations/i1').flush(null);
    await avanzar(fixture);

    http.expectOne('/api/v1/organizations/me/invitations').flush([]);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Invitación revocada');
  });

  it('no tiene violaciones de accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    try {
      const fixture = await crearYCargar(http, [INVITACION]);
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });
});
