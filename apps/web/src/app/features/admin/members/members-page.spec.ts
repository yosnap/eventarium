import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { MembersPage } from './members-page';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function pagina(total: number, offset: number) {
  return {
    items: [
      {
        id: '1',
        user_id: 'u1',
        email: 'persona@example.com',
        first_name: 'Persona',
        last_name: 'De Prueba',
        role_id: 'r1',
        role_key: 'owner',
        profile_data: {},
      },
    ],
    total,
    limit: 20,
    offset,
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** `InvitationsPanel` (fase 2) pide sus dos listas al construirse: se agota aparte. */
async function flushPanelDeInvitaciones(
  http: HttpTestingController,
  fixture: ComponentFixture<unknown>,
): Promise<void> {
  http.expectOne((peticion) => peticion.url === '/api/v1/organizations/me/invitations').flush([]);
  http.expectOne((peticion) => peticion.url === '/api/v1/roles').flush([]);
  await avanzar(fixture);
  // `InvitationsPanel.cargar()` espera `Promise.all(...)`: hace falta un
  // segundo ciclo de estabilidad para que el `finally` que apaga `cargando`
  // se refleje en el DOM (mismo ajuste que `invitations-panel.spec.ts`).
  await avanzar(fixture);
}

describe('MembersPage', () => {
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

  it('lista los miembros con su rol, sin paginación cuando cabe en una página', async () => {
    const fixture = TestBed.createComponent(MembersPage);
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/members')
      .flush(pagina(1, 0));
    await avanzar(fixture);
    await flushPanelDeInvitaciones(http, fixture);

    expect(fixture.nativeElement.textContent).toContain('Persona De Prueba');
    expect(fixture.nativeElement.textContent).toContain('owner');
    expect(fixture.nativeElement.querySelector('nav.paginacion')).toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('la tabla usa app-data-table con caption y scroll alcanzable con teclado', async () => {
    const fixture = TestBed.createComponent(MembersPage);
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/members')
      .flush(pagina(1, 0));
    await avanzar(fixture);
    await flushPanelDeInvitaciones(http, fixture);

    const contenedor = fixture.nativeElement.querySelector('app-data-table') as HTMLElement | null;
    expect(contenedor).not.toBeNull();

    const tabla = contenedor!.querySelector('table') as HTMLTableElement;
    expect(tabla.querySelector('caption')?.textContent?.trim()).toBeTruthy();
    expect(tabla.querySelectorAll('th[scope="col"]').length).toBe(3);
    expect(tabla.querySelectorAll('tbody tr').length).toBe(1);

    const ranura = contenedor!.querySelector('.ranura-scroll') as HTMLElement;
    expect(ranura.getAttribute('tabindex')).toBe('0');
    expect(ranura.getAttribute('role')).toBe('region');
    expect(ranura.getAttribute('aria-label')).toBeTruthy();
  });

  it('muestra paginación cuando hay más de una página y pide la siguiente', async () => {
    const fixture = TestBed.createComponent(MembersPage);
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/members')
      .flush(pagina(25, 0));
    await avanzar(fixture);
    await flushPanelDeInvitaciones(http, fixture);

    expect(fixture.nativeElement.textContent).toContain('Página 1 de 2');

    const botonSiguiente = Array.from(
      fixture.nativeElement.querySelectorAll('nav.paginacion button'),
    ).find((boton) => (boton as HTMLButtonElement).textContent?.includes('Siguiente')) as
      HTMLButtonElement | undefined;
    botonSiguiente?.click();
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/organizations/me/members',
    );
    expect(peticion.request.params.get('offset')).toBe('20');
    peticion.flush(pagina(25, 20));
  });
  it('no tiene violaciones de accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    try {
      const fixture = TestBed.createComponent(MembersPage);
      await avanzar(fixture);
      http
        .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/members')
        .flush(pagina(1, 0));
      await avanzar(fixture);
      await flushPanelDeInvitaciones(http, fixture);

      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });
});
