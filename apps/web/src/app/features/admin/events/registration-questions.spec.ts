import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { RegistrationQuestions } from './registration-questions';

const PREGUNTAS = [
  {
    id: 'q1',
    type: 'short_text',
    label: '¿Alergias?',
    required: false,
    sort_order: 0,
    options: null,
  },
  {
    id: 'q2',
    type: 'single_choice',
    label: 'Talla de camiseta',
    required: true,
    sort_order: 1,
    options: ['S', 'M', 'L'],
  },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('RegistrationQuestions', () => {
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
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lista las preguntas existentes y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(RegistrationQuestions);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
      .flush(PREGUNTAS);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('¿Alergias?');
    expect(fixture.nativeElement.textContent).toContain('Talla de camiseta');
    expect(fixture.nativeElement.textContent).toContain('S, M, L');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('añade una pregunta de texto corto con el formulario', async () => {
    const fixture = TestBed.createComponent(RegistrationQuestions);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
      .flush([]);
    await avanzar(fixture);

    const etiqueta = fixture.nativeElement.querySelector(
      '#pregunta-etiqueta-nueva',
    ) as HTMLInputElement;
    etiqueta.value = 'Nueva pregunta';
    etiqueta.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) =>
        peticion.url === '/api/v1/events/e1/registration-questions' && peticion.method === 'POST',
    );
    expect(peticion.request.body.label).toBe('Nueva pregunta');
    expect(peticion.request.body.type).toBe('short_text');
    peticion.flush({
      id: 'q3',
      type: 'short_text',
      label: 'Nueva pregunta',
      required: false,
      sort_order: 0,
      options: null,
    });
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
      .flush([]);
  });

  it('exige al menos dos opciones para una pregunta de opción única', async () => {
    const fixture = TestBed.createComponent(RegistrationQuestions);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
      .flush([]);
    await avanzar(fixture);

    const etiqueta = fixture.nativeElement.querySelector(
      '#pregunta-etiqueta-nueva',
    ) as HTMLInputElement;
    etiqueta.value = 'Elige una opción';
    etiqueta.dispatchEvent(new Event('input'));
    const tipo = fixture.nativeElement.querySelector('#pregunta-tipo-nueva') as HTMLSelectElement;
    tipo.value = 'single_choice';
    tipo.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('Añade al menos dos opciones.');
  });

  it('muestra el error de la API al borrar una pregunta con respuestas (409)', async () => {
    const fixture = TestBed.createComponent(RegistrationQuestions);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
      .flush(PREGUNTAS);
    await avanzar(fixture);

    const botonesEliminar = Array.from(fixture.nativeElement.querySelectorAll('button')).filter(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Eliminar',
    ) as HTMLButtonElement[];
    botonesEliminar[0]?.click();
    await avanzar(fixture);

    const botonConfirmar = Array.from(fixture.nativeElement.querySelectorAll('button')).find(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === '¿Seguro?',
    ) as HTMLButtonElement | undefined;
    botonConfirmar?.click();
    await avanzar(fixture);

    http
      .expectOne(
        (peticion) =>
          peticion.url === '/api/v1/events/e1/registration-questions/q1' &&
          peticion.method === 'DELETE',
      )
      .flush(
        { title: 'Conflicto', detail: 'La pregunta ya tiene respuestas.' },
        { status: 409, statusText: 'Conflict' },
      );
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('La pregunta ya tiene respuestas.');
  });
});
