import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { MemberForm } from './member-form';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const ROLES = [
  { id: 'r1', key: 'owner', name: 'Propietario', profile_fields: [] },
  {
    id: 'r2',
    key: 'speaker',
    name: 'Ponente',
    profile_fields: [
      { key: 'bio', label: 'Biografía', field_type: 'textarea', options: null, is_required: true },
    ],
  },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('MemberForm', () => {
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

  it('exige los campos base antes de enviar, y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(MemberForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('correo');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('cambia los campos de perfil pedidos al cambiar de rol', async () => {
    const fixture = TestBed.createComponent(MemberForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).not.toContain('Biografía');

    const selectorRol = fixture.nativeElement.querySelector('#miembro-rol') as HTMLSelectElement;
    selectorRol.value = 'r2';
    selectorRol.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Biografía');
  });

  it('exige los campos de perfil obligatorios del rol elegido', async () => {
    const fixture = TestBed.createComponent(MemberForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    const selectorRol = fixture.nativeElement.querySelector('#miembro-rol') as HTMLSelectElement;
    selectorRol.value = 'r2';
    selectorRol.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const campoCorreo = fixture.nativeElement.querySelector('#miembro-correo') as HTMLInputElement;
    campoCorreo.value = 'persona@example.com';
    campoCorreo.dispatchEvent(new Event('input'));
    const campoNombre = fixture.nativeElement.querySelector('#miembro-nombre') as HTMLInputElement;
    campoNombre.value = 'Persona';
    campoNombre.dispatchEvent(new Event('input'));
    const campoApellidos = fixture.nativeElement.querySelector(
      '#miembro-apellidos',
    ) as HTMLInputElement;
    campoApellidos.value = 'De Prueba';
    campoApellidos.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('Biografía» es obligatorio');
  });

  it('añade el miembro con los datos del formulario', async () => {
    const fixture = TestBed.createComponent(MemberForm);
    await avanzar(fixture);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    const selectorRol = fixture.nativeElement.querySelector('#miembro-rol') as HTMLSelectElement;
    selectorRol.value = 'r1';
    selectorRol.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const campoCorreo = fixture.nativeElement.querySelector('#miembro-correo') as HTMLInputElement;
    campoCorreo.value = 'persona@example.com';
    campoCorreo.dispatchEvent(new Event('input'));
    const campoNombre = fixture.nativeElement.querySelector('#miembro-nombre') as HTMLInputElement;
    campoNombre.value = 'Persona';
    campoNombre.dispatchEvent(new Event('input'));
    const campoApellidos = fixture.nativeElement.querySelector(
      '#miembro-apellidos',
    ) as HTMLInputElement;
    campoApellidos.value = 'De Prueba';
    campoApellidos.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/organizations/me/members');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body.email).toBe('persona@example.com');
    expect(peticion.request.body.role_id).toBe('r1');
    peticion.flush({ id: 'm1' });
  });
});
