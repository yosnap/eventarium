import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { errorInterceptor } from '../../../core/api/error.interceptor';
import { AcceptedPolicies } from './accepted-policies';
import { EventPoliciesPage } from './event-policies-page';
import { EventPoliciesWarning } from './event-policies-warning';
import { type PoliticaDeEvento, type PoliticasDeEvento } from './policies-types';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const URL = '/api/v1/events/e1/policies';

function version(content: string, id = 'v-org') {
  return {
    version_id: id,
    kind: 'condiciones' as const,
    version: 1,
    content,
    created_at: '2026-09-23T10:00:00Z',
  };
}

function items(condiciones: Partial<PoliticaDeEvento> = {}): PoliticaDeEvento[] {
  return [
    {
      kind: 'condiciones',
      origin: 'organizacion',
      current: version('De la **organización**'),
      organization: version('De la **organización**'),
      ...condiciones,
    },
    { kind: 'reembolsos', origin: 'ninguno', current: null, organization: null },
    { kind: 'privacidad', origin: 'ninguno', current: null, organization: null },
    { kind: 'otras', origin: 'ninguno', current: null, organization: null },
  ];
}

function respuesta(canEdit = true, lista = items()): PoliticasDeEvento {
  return { can_edit: canEdit, items: lista };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar(): HttpTestingController {
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
      provideHttpClient(withInterceptors([errorInterceptor])),
      provideHttpClientTesting(),
    ],
  });
  return TestBed.inject(HttpTestingController);
}

describe('EventPoliciesPage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    http = configurar();
  });

  afterEach(() => http.verify());

  async function montar(
    datos = respuesta(),
    estado = 'published',
  ): Promise<ComponentFixture<EventPoliciesPage>> {
    const fixture = TestBed.createComponent(EventPoliciesPage);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne(URL).flush(datos);
    http.expectOne('/api/v1/events/e1').flush({ status: estado });
    await avanzar(fixture);
    await avanzar(fixture);
    return fixture;
  }

  function radio(raiz: HTMLElement, kind: string, valor: string): HTMLInputElement {
    return raiz.querySelector(`input[name="modo-${kind}"][value="${valor}"]`) as HTMLInputElement;
  }

  it('distingue heredado, propio y sin texto', async () => {
    const fixture = await montar();
    const raiz = fixture.nativeElement as HTMLElement;
    expect(radio(raiz, 'condiciones', 'heredar').checked).toBe(true);
    expect(raiz.textContent).toContain('Se aplica el de la organización:');
    expect(raiz.textContent).toContain('La organización no tiene este texto.');
    expect(raiz.textContent).toContain('profesional del derecho');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('elegir texto propio abre el editor y avisa si el evento está publicado', async () => {
    const fixture = await montar();
    const raiz = fixture.nativeElement as HTMLElement;
    radio(raiz, 'reembolsos', 'propio').click();
    await avanzar(fixture);
    expect(raiz.querySelector('app-policy-editor')).not.toBeNull();
    expect(raiz.textContent).toContain('tendrá que volver a aceptar las condiciones');
  });

  it('volver a heredar envía content: null', async () => {
    const propio = items({ origin: 'evento', current: version('Propio', 'v-ev') });
    const fixture = await montar(respuesta(true, propio));
    const raiz = fixture.nativeElement as HTMLElement;
    expect(radio(raiz, 'condiciones', 'propio').checked).toBe(true);

    radio(raiz, 'condiciones', 'heredar').click();
    await avanzar(fixture);
    const peticion = http.expectOne(`${URL}/condiciones`);
    expect(peticion.request.body).toEqual({ content: null });
    peticion.flush(respuesta());
    await avanzar(fixture);
  });

  it('si falla volver a heredar, el selector sigue en texto propio', async () => {
    const propio = items({ origin: 'evento', current: version('Propio', 'v-ev') });
    const fixture = await montar(respuesta(true, propio));
    const raiz = fixture.nativeElement as HTMLElement;

    radio(raiz, 'condiciones', 'heredar').click();
    await avanzar(fixture);
    http
      .expectOne(`${URL}/condiciones`)
      .flush({ detail: 'Error' }, { status: 500, statusText: 'Server Error' });
    await avanzar(fixture);
    await avanzar(fixture);
    expect(radio(raiz, 'condiciones', 'propio').checked).toBe(true);
    expect(raiz.querySelector('app-policy-editor')).not.toBeNull();
  });

  it('guardar un documento no cierra el editor abierto de otro', async () => {
    const fixture = await montar();
    const raiz = fixture.nativeElement as HTMLElement;
    radio(raiz, 'reembolsos', 'propio').click();
    radio(raiz, 'otras', 'propio').click();
    await avanzar(fixture);
    expect(raiz.querySelectorAll('app-policy-editor').length).toBe(2);

    const [reembolsos] = Array.from(raiz.querySelectorAll('app-policy-editor'));
    const area = reembolsos.querySelector('textarea') as HTMLTextAreaElement;
    area.value = 'Sin reembolsos';
    area.dispatchEvent(new Event('input'));
    await avanzar(fixture);
    (reembolsos.querySelector('button[type=button]:not([role=tab])') as HTMLButtonElement).click();
    const guardado = items();
    guardado[1] = {
      kind: 'reembolsos',
      origin: 'evento',
      current: { ...version('Sin reembolsos', 'v-r'), kind: 'reembolsos' },
      organization: null,
    };
    http.expectOne(`${URL}/reembolsos`).flush(respuesta(true, guardado));
    await avanzar(fixture);
    await avanzar(fixture);
    // «Otras» seguía en «texto propio» sin guardar: su editor sigue abierto.
    expect(radio(raiz, 'otras', 'propio').checked).toBe(true);
    expect(raiz.querySelectorAll('app-policy-editor').length).toBe(2);
  });

  it('sin permiso de escritura no hay selector ni editor, y lo explica', async () => {
    const propio = items({ origin: 'evento', current: version('Texto **propio**', 'v-ev') });
    const fixture = await montar(respuesta(false, propio));
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('app-radio-group, app-policy-editor')).toBeNull();
    expect(raiz.textContent).toContain('Solo quien gestiona la organización');
    expect(raiz.textContent).toContain('Este evento usa un texto propio:');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });
});

describe('EventPoliciesWarning', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    http = configurar();
  });

  afterEach(() => http.verify());

  async function montar(datos: PoliticasDeEvento): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(EventPoliciesWarning);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    http.expectOne(URL).flush(datos);
    await avanzar(fixture);
    return fixture.nativeElement as HTMLElement;
  }

  it('avisa si el evento no tiene ningún texto vigente', async () => {
    const sinNada = items({ origin: 'ninguno', current: null, organization: null });
    const raiz = await montar(respuesta(true, sinNada));
    expect(raiz.textContent).toContain('Este evento no tiene condiciones propias');
    expect(raiz.querySelector('a')?.getAttribute('href')).toBe('/dashboard/events/e1/politicas');
  });

  it('no avisa si hay algún texto vigente', async () => {
    const raiz = await montar(respuesta());
    expect(raiz.textContent?.trim()).toBe('');
  });
});

describe('AcceptedPolicies', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    http = configurar();
  });

  afterEach(() => http.verify());

  it('enseña el texto exacto de la versión aceptada', async () => {
    const fixture = TestBed.createComponent(AcceptedPolicies);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.componentRef.setInput('aceptadasEl', '2026-09-23T10:00:00Z');
    fixture.componentRef.setInput('versiones', [
      { version_id: 'v3', kind: 'reembolsos', version: 3 },
    ]);
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('Política de reembolsos, versión 3');

    (raiz.querySelector('button') as HTMLButtonElement).click();
    http.expectOne(`${URL}/versions/v3`).flush({
      version_id: 'v3',
      kind: 'reembolsos',
      version: 3,
      content: 'Reembolso del **50 %**',
      created_at: '2026-09-20T10:00:00Z',
    });
    await avanzar(fixture);
    await avanzar(fixture);
    expect(raiz.querySelector('app-markdown-seguro strong')?.textContent).toBe('50 %');
  });

  it('sin aceptación indica que el evento no tenía textos', async () => {
    const fixture = TestBed.createComponent(AcceptedPolicies);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'no tenía condiciones propias',
    );
  });
});
