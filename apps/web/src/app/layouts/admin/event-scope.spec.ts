import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, inject, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { afterEach, describe, expect, it } from 'vitest';

import { EventScope } from './event-scope';

@Component({ selector: 'app-anfitrion-de-prueba', template: '' })
class AnfitrionDePrueba {
  readonly scope = inject(EventScope);
}

const routes = [
  { path: 'admin/events', component: AnfitrionDePrueba },
  { path: 'admin/events/nuevo', component: AnfitrionDePrueba },
  { path: 'admin/events/:id', component: AnfitrionDePrueba },
  { path: 'admin/events/:eventId/check-in', component: AnfitrionDePrueba },
  { path: 'admin/roles/:id', component: AnfitrionDePrueba },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar() {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(routes),
      provideHttpClient(),
      provideHttpClientTesting(),
    ],
  });
}

describe('EventScope', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('sin evento en la ruta: eventId es null', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/events');
    const fixture = TestBed.createComponent(AnfitrionDePrueba);
    await avanzar(fixture);

    expect(fixture.componentInstance.scope.eventId()).toBeNull();
  });

  it('con `:id` activo: resuelve nombre y modo de inscripción', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/events/e1');
    const fixture = TestBed.createComponent(AnfitrionDePrueba);
    await avanzar(fixture);

    expect(fixture.componentInstance.scope.eventId()).toBe('e1');
    http.expectOne('/api/v1/events/e1').flush({ title: 'IA Week', registration_mode: 'paid' });
    await avanzar(fixture);

    expect(fixture.componentInstance.scope.nombreEvento()).toBe('IA Week');
    expect(fixture.componentInstance.scope.registrationMode()).toBe('paid');
    expect(fixture.componentInstance.scope.falloCarga()).toBe(false);
  });

  it('con `:eventId` activo (check-in): también entra en el ámbito de evento', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/events/e1/check-in');
    const fixture = TestBed.createComponent(AnfitrionDePrueba);
    await avanzar(fixture);

    expect(fixture.componentInstance.scope.eventId()).toBe('e1');
    http.expectOne('/api/v1/events/e1').flush({ title: 'IA Week', registration_mode: 'free' });
    await avanzar(fixture);
  });

  it('si la carga del nombre falla, `falloCarga` se activa sin romper', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/events/e1');
    const fixture = TestBed.createComponent(AnfitrionDePrueba);
    await avanzar(fixture);

    http
      .expectOne('/api/v1/events/e1')
      .flush('fallo', { status: 500, statusText: 'Error del servidor' });
    await avanzar(fixture);

    expect(fixture.componentInstance.scope.falloCarga()).toBe(true);
    expect(fixture.componentInstance.scope.nombreEvento()).toBeNull();
  });

  it('en `/admin/roles/:id`, que también tiene un parámetro `id`, no activa el ámbito de evento', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/roles/r1');
    const fixture = TestBed.createComponent(AnfitrionDePrueba);
    await avanzar(fixture);

    expect(fixture.componentInstance.scope.eventId()).toBeNull();
    // Ninguna petición a /events/r1: si se hubiera disparado, `http.verify()` en
    // `afterEach` fallaría.
  });

  it('cachea el nombre del evento: no repite la petición al volver al mismo id', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/events/e1');
    const fixture = TestBed.createComponent(AnfitrionDePrueba);
    await avanzar(fixture);
    http.expectOne('/api/v1/events/e1').flush({ title: 'IA Week', registration_mode: 'free' });
    await avanzar(fixture);

    await router.navigateByUrl('/admin/events');
    await avanzar(fixture);
    await router.navigateByUrl('/admin/events/e1');
    await avanzar(fixture);

    expect(fixture.componentInstance.scope.nombreEvento()).toBe('IA Week');
    // Ninguna petición pendiente: si hubiera repetido la llamada, `http.verify()`
    // en `afterEach` fallaría.
  });
});
