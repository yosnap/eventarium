import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { errorInterceptor } from '../../../core/api/error.interceptor';
import { OrganizationPoliciesPage } from './organization-policies-page';
import { type PoliticasDeOrganizacion } from './policies-types';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const URL = '/api/v1/organizations/me/policies';

function respuesta(
  canEdit = true,
  condiciones: string | null = 'Condiciones **vigentes**',
): PoliticasDeOrganizacion {
  return {
    can_edit: canEdit,
    items: [
      {
        kind: 'condiciones',
        current: condiciones
          ? {
              version_id: 'v1',
              kind: 'condiciones',
              version: 2,
              content: condiciones,
              created_at: '2026-09-23T10:00:00Z',
            }
          : null,
        last_version: 2,
      },
      { kind: 'reembolsos', current: null, last_version: null },
      { kind: 'privacidad', current: null, last_version: null },
      { kind: 'otras', current: null, last_version: null },
    ],
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('OrganizationPoliciesPage', () => {
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
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function montar(datos = respuesta()): Promise<ComponentFixture<OrganizationPoliciesPage>> {
    const fixture = TestBed.createComponent(OrganizationPoliciesPage);
    fixture.detectChanges();
    http.expectOne(URL).flush(datos);
    await avanzar(fixture);
    return fixture;
  }

  it('muestra el aviso de responsabilidad y los cuatro documentos', async () => {
    const fixture = await montar();
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('Eventarium no los revisa');
    expect(raiz.textContent).toContain('profesional del derecho');
    expect(raiz.querySelectorAll('app-policy-editor').length).toBe(4);
    expect(raiz.textContent).toContain('Versión 2 guardada.');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('la vista previa sanea el texto: un script no se pinta', async () => {
    const fixture = await montar(respuesta(true, 'Hola <script>alert(1)</script> **mundo**'));
    const raiz = fixture.nativeElement as HTMLElement;
    const vista = raiz.querySelector('app-policy-editor .vista') as HTMLElement;
    expect(vista.querySelector('script')).toBeNull();
    expect(vista.querySelector('strong')?.textContent).toBe('mundo');
  });

  it('guardar envía el texto al PUT de su tipo', async () => {
    const fixture = await montar();
    const raiz = fixture.nativeElement as HTMLElement;
    const area = raiz.querySelectorAll('textarea')[1] as HTMLTextAreaElement;
    area.value = 'Sin reembolsos';
    area.dispatchEvent(new Event('input'));
    await avanzar(fixture);
    (
      raiz
        .querySelectorAll('app-policy-editor')[1]
        .querySelector('button[type=button]:not([role=tab])') as HTMLButtonElement
    ).click();

    const peticion = http.expectOne(`${URL}/reembolsos`);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body).toEqual({ content: 'Sin reembolsos' });
    peticion.flush(respuesta());
    await avanzar(fixture);
  });

  it('un 409 al guardar muestra el mensaje y recarga', async () => {
    const fixture = await montar();
    const raiz = fixture.nativeElement as HTMLElement;
    const area = raiz.querySelector('textarea') as HTMLTextAreaElement;
    area.value = 'Otro texto';
    area.dispatchEvent(new Event('input'));
    await avanzar(fixture);
    (
      raiz.querySelector(
        'app-policy-editor button[type=button]:not([role=tab])',
      ) as HTMLButtonElement
    ).click();

    http
      .expectOne(`${URL}/condiciones`)
      .flush(
        { detail: 'Otra persona ha guardado este texto a la vez; recarga y vuelve a intentarlo.' },
        { status: 409, statusText: 'Conflict' },
      );
    // La recarga sale en la continuación del `catch`: un ciclo más.
    await avanzar(fixture);
    await avanzar(fixture);
    http.expectOne(URL).flush(respuesta());
    await avanzar(fixture);
    expect(raiz.textContent).toContain('Otra persona ha guardado este texto a la vez');
    // El borrador no se pierde con la recarga.
    expect((raiz.querySelector('textarea') as HTMLTextAreaElement).value).toBe('Otro texto');
  });

  it('retirar pide confirmación y guarda un texto vacío', async () => {
    const fixture = await montar();
    const raiz = fixture.nativeElement as HTMLElement;
    const retirar = Array.from(raiz.querySelectorAll('button')).find(
      (boton) => boton.textContent?.trim() === 'Retirar',
    ) as HTMLButtonElement;
    retirar.click();
    await avanzar(fixture);
    expect(raiz.textContent).toContain('Las inscripciones anteriores conservan la versión');

    const confirmar = Array.from(raiz.querySelectorAll('button')).find(
      (boton) => boton.textContent?.trim() === 'Sí, retirar',
    ) as HTMLButtonElement;
    confirmar.click();
    const peticion = http.expectOne(`${URL}/condiciones`);
    expect(peticion.request.body).toEqual({ content: '' });
    peticion.flush(respuesta(true, null));
    await avanzar(fixture);
  });

  it('sin permiso de escritura se ve en solo lectura, sin editor', async () => {
    const fixture = await montar(respuesta(false));
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('app-policy-editor')).toBeNull();
    expect(raiz.textContent).toContain('Solo quien gestiona la organización');
    expect(raiz.querySelector('app-markdown-seguro strong')?.textContent).toBe('vigentes');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });
});
