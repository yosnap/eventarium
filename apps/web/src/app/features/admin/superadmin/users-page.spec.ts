import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { AuthService } from '../../../core/auth/auth.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { UsersPage } from './users-page';

const LISTA_URL = '/api/v1/admin/users';
const ORGS_URL = '/api/v1/admin/organizations';

const USUARIO_RESUMEN = {
  id: 'u1',
  email: 'ana@ejemplo.com',
  first_name: 'Ana',
  last_name: 'Pérez',
  is_active: true,
  platform_role: null,
  created_at: '2026-09-01T10:00:00Z',
  organization_names: 'IA Week',
};

const USUARIO_DETALLE = {
  id: 'u1',
  email: 'ana@ejemplo.com',
  first_name: 'Ana',
  last_name: 'Pérez',
  is_active: true,
  platform_role: null,
  notify_similar_events: false,
  created_at: '2026-09-01T10:00:00Z',
  organizations: [{ organization_id: 'org-1', organization_name: 'Acme', role_name: 'organizer' }],
  registrations_count: 3,
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar(esSuperadmin: boolean, miPropioId = 'yo'): void {
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
      {
        provide: AuthService,
        useValue: { currentUser: signal({ id: miPropioId, is_superadmin: esSuperadmin }) },
      },
    ],
  });
}

describe('UsersPage', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('carga el listado y no tiene violaciones de accesibilidad', async () => {
    configurar(true);
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(UsersPage);
    await avanzar(fixture);

    http.expectOne(ORGS_URL).flush([{ id: 'org-1', name: 'Acme', slug: 'acme', is_active: true }]);
    http.expectOne((r) => r.url === LISTA_URL).flush({
      items: [USUARIO_RESUMEN],
      total: 1,
      limit: 20,
      offset: 0,
    });
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('ana@ejemplo.com');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('error del servidor: se muestra en role="alert"', async () => {
    configurar(true);
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(UsersPage);
    await avanzar(fixture);

    http.expectOne(ORGS_URL).flush([]);
    http.expectOne((r) => r.url === LISTA_URL).flush(
      { detail: 'fallo' },
      { status: 500, statusText: 'Error' },
    );
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('[role="alert"]')).not.toBeNull();
  });

  it('seleccionar una fila carga el detalle', async () => {
    configurar(true);
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(UsersPage);
    await avanzar(fixture);
    http.expectOne(ORGS_URL).flush([]);
    http.expectOne((r) => r.url === LISTA_URL).flush({
      items: [USUARIO_RESUMEN],
      total: 1,
      limit: 20,
      offset: 0,
    });
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    raiz.querySelector<HTMLButtonElement>('.fila-boton')?.click();
    await avanzar(fixture);

    http.expectOne((r) => r.url === `${LISTA_URL}/u1`).flush(USUARIO_DETALLE);
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Acme');
    expect(raiz.textContent).toContain('organizer');
  });

  it('soporte (no superadmin) ve el detalle pero no los controles de escritura', async () => {
    configurar(false);
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(UsersPage);
    await avanzar(fixture);
    http.expectOne(ORGS_URL).flush([]);
    http.expectOne((r) => r.url === LISTA_URL).flush({
      items: [USUARIO_RESUMEN],
      total: 1,
      limit: 20,
      offset: 0,
    });
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    raiz.querySelector<HTMLButtonElement>('.fila-boton')?.click();
    await avanzar(fixture);
    http.expectOne((r) => r.url === `${LISTA_URL}/u1`).flush(USUARIO_DETALLE);
    await avanzar(fixture);

    expect(raiz.querySelector('.acciones-detalle')).toBeNull();
  });

  it('desactivar exige confirmación en dos pasos', async () => {
    configurar(true);
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(UsersPage);
    await avanzar(fixture);
    http.expectOne(ORGS_URL).flush([]);
    http.expectOne((r) => r.url === LISTA_URL).flush({
      items: [USUARIO_RESUMEN],
      total: 1,
      limit: 20,
      offset: 0,
    });
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    raiz.querySelector<HTMLButtonElement>('.fila-boton')?.click();
    await avanzar(fixture);
    http.expectOne((r) => r.url === `${LISTA_URL}/u1`).flush(USUARIO_DETALLE);
    await avanzar(fixture);

    const botones = () => Array.from(raiz.querySelectorAll('.acciones-detalle button'));
    const desactivarBtn = botones().find((b) => b.textContent?.includes('Desactivar'));
    expect(desactivarBtn).toBeTruthy();
    desactivarBtn?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    // Tras el primer clic aparece el botón de confirmación, no una petición aún.
    const confirmar = botones().find((b) => b.textContent?.includes('Confirmar'));
    expect(confirmar).toBeTruthy();

    confirmar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);
    http.expectOne((r) => r.url === `${LISTA_URL}/u1/deactivate`).flush({});
    await avanzar(fixture);

    http.expectOne((r) => r.url === `${LISTA_URL}/u1`).flush({
      ...USUARIO_DETALLE,
      is_active: false,
      first_name: null,
      last_name: null,
    });
    await avanzar(fixture);
    http.expectOne((r) => r.url === LISTA_URL).flush({ items: [], total: 0, limit: 20, offset: 0 });
    await avanzar(fixture);
  });
});
