import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { describe, expect, it } from 'vitest';

import { idiomaInterceptor } from './idioma.interceptor';
import { IDIOMA } from './idioma.service';

function configurar() {
  TestBed.configureTestingModule({
    providers: [
      { provide: IDIOMA, useValue: 'en-US' },
      provideHttpClient(withInterceptors([idiomaInterceptor])),
      provideHttpClientTesting(),
    ],
  });
  return {
    http: TestBed.inject(HttpClient),
    controlador: TestBed.inject(HttpTestingController),
  };
}

describe('idiomaInterceptor', () => {
  it('pide a la API las respuestas en el idioma de la página', async () => {
    const { http, controlador } = configurar();
    const respuesta = firstValueFrom(http.get('/api/v1/users/me'));
    const peticion = controlador.expectOne('/api/v1/users/me');
    expect(peticion.request.headers.get('Accept-Language')).toBe('en-US');
    peticion.flush({});
    await respuesta;
  });

  it('no manda la cabecera a servicios de terceros', async () => {
    const { http, controlador } = configurar();
    const respuesta = firstValueFrom(http.get('https://tercero.example/datos'));
    const peticion = controlador.expectOne('https://tercero.example/datos');
    expect(peticion.request.headers.has('Accept-Language')).toBe(false);
    peticion.flush({});
    await respuesta;
  });
});
