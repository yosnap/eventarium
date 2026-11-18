import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { beforeEach, describe, expect, it } from 'vitest';

import { ApiError, errorInterceptor } from './error.interceptor';

describe('errorInterceptor', () => {
  let http: HttpClient;
  let controlador: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    controlador = TestBed.inject(HttpTestingController);
  });

  async function mensajeDe(cuerpo: object): Promise<string> {
    const peticion = firstValueFrom(http.post('/api/v1/x', {}));
    controlador.expectOne('/api/v1/x').flush(cuerpo, { status: 422, statusText: 'Unprocessable' });
    try {
      await peticion;
      throw new Error('debía fallar');
    } catch (error) {
      return (error as ApiError).message;
    }
  }

  const GENERICO = 'La petición no supera la validación.';

  it('en un 422, el mensaje de un validador propio sustituye al genérico', async () => {
    expect(
      await mensajeDe({
        detail: GENERICO,
        errors: [
          { campo: 'body.title', mensaje: 'Debe tener al menos 1 caracteres.', propio: false },
          {
            campo: 'body',
            mensaje: 'La fecha de fin debe ser posterior a la de inicio.',
            propio: true,
          },
        ],
      }),
    ).toBe('La fecha de fin debe ser posterior a la de inicio.');
  });

  it('los mensajes genéricos de un campo no se enseñan: queda el genérico', async () => {
    expect(
      await mensajeDe({
        detail: GENERICO,
        errors: [
          { campo: 'body.title', mensaje: 'Debe tener al menos 1 caracteres.', propio: false },
        ],
      }),
    ).toBe(GENERICO);
  });

  it('sin el campo «propio», reconoce el prefijo de una API anterior', async () => {
    expect(
      await mensajeDe({
        detail: GENERICO,
        errors: [
          {
            campo: 'body',
            mensaje: 'Value error, La fecha de fin debe ser posterior a la de inicio.',
          },
        ],
      }),
    ).toBe('La fecha de fin debe ser posterior a la de inicio.');
  });

  it('los mensajes técnicos de Pydantic sin «propio» no se enseñan', async () => {
    expect(
      await mensajeDe({
        detail: GENERICO,
        errors: [{ campo: 'body.title', mensaje: 'String should have at least 1 character' }],
      }),
    ).toBe(GENERICO);
  });
});
