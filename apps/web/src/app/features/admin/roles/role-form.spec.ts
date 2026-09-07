import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { RoleForm } from './role-form';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const PERSONA = { permissions: ['organizations:read', 'roles:read', 'roles:write'] };

const ROLES = [
  {
    id: '1',
    key: 'owner',
    name: 'Propietario',
    description: null,
    is_system: true,
    system_template_key: 'owner',
    permissions: ['organizations:read', 'organizations:write'],
    profile_fields: [
      {
        id: 'f1',
        key: 'cargo',
        label: 'Cargo',
        field_type: 'text',
        options: null,
        is_required: false,
        is_locked: true,
        sort_order: 10,
      },
    ],
  },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar(id: string) {
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
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap({ id }) } },
      },
    ],
  });
}

describe('RoleForm — crear', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    configurar('nuevo');
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('exige clave y nombre antes de enviar, y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(RoleForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/users/me').flush(PERSONA);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('identificador');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('deshabilita los permisos que el actor no posee', async () => {
    const fixture = TestBed.createComponent(RoleForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/users/me').flush(PERSONA);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);
    await avanzar(fixture);

    const casillas = Array.from(
      fixture.nativeElement.querySelectorAll('.permiso input[type="checkbox"]'),
    ) as HTMLInputElement[];
    // La persona actora tiene 3 de los 8 permisos: el resto debe quedar deshabilitado.
    const deshabilitadas = casillas.filter((casilla) => casilla.disabled);
    expect(deshabilitadas.length).toBe(5);
  });

  it('crea el rol con los datos del formulario', async () => {
    const fixture = TestBed.createComponent(RoleForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/users/me').flush(PERSONA);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);
    await avanzar(fixture);

    const campoClave = fixture.nativeElement.querySelector('#rol-clave') as HTMLInputElement;
    campoClave.value = 'presentador';
    campoClave.dispatchEvent(new Event('input'));
    const campoNombre = fixture.nativeElement.querySelector('#rol-nombre') as HTMLInputElement;
    campoNombre.value = 'Presentador';
    campoNombre.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/roles');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body.key).toBe('presentador');
    expect(peticion.request.body.name).toBe('Presentador');
    peticion.flush({ id: '2' });
  });
});

describe('RoleForm — editar', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    configurar('1');
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('carga el rol existente y muestra los campos bloqueados como no editables', async () => {
    const fixture = TestBed.createComponent(RoleForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/users/me').flush(PERSONA);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);
    await avanzar(fixture);

    expect((fixture.nativeElement.querySelector('#rol-nombre') as HTMLInputElement).value).toBe(
      'Propietario',
    );
    expect(fixture.nativeElement.textContent).toContain('viene de la plantilla');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
