import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { OrganizationPublicPage } from './organization-public-page';

const PERFIL = {
  slug: 'acme',
  name: 'Acme Eventos',
  description: 'Organizamos encuentros de la comunidad.',
  website: 'https://acme.example',
  address: 'Calle Mayor 1, Madrid',
  logo_url: null,
  social_links: [{ kind: 'linkedin', url: 'https://linkedin.com/company/acme' }],
};

function evento(slug: string, titulo: string) {
  return {
    slug,
    organization: { slug: 'acme' },
    title: titulo,
    summary: null,
    timezone: 'Europe/Madrid',
    starts_at: '2026-10-05T09:00:00Z',
    location_name: 'Palacio',
    city: 'Madrid',
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('OrganizationPublicPage', () => {
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
    document.documentElement.removeAttribute('data-theme');
  });

  function abrir() {
    const fixture = TestBed.createComponent(OrganizationPublicPage);
    fixture.componentRef.setInput('org', 'acme');
    return fixture;
  }

  function responder(proximos: unknown[], pasados: unknown[], totalPasados = pasados.length) {
    http.expectOne('/api/v1/public/organizations/acme').flush(PERFIL);
    http
      .expectOne((p) => p.url.includes('/events') && p.url.includes('when=upcoming'))
      .flush({ items: proximos, total: proximos.length });
    http
      .expectOne((p) => p.url.includes('/events') && p.url.includes('when=past'))
      .flush({ items: pasados, total: totalPasados });
  }

  it('muestra el perfil y sus eventos próximos y pasados, sin violaciones de accesibilidad', async () => {
    const fixture = abrir();
    fixture.detectChanges();
    responder([evento('proximo', 'Encuentro próximo')], [evento('viejo', 'Encuentro viejo')]);
    await avanzar(fixture);

    const texto: string = fixture.nativeElement.textContent;
    expect(texto).toContain('Acme Eventos');
    expect(texto).toContain('Organizamos encuentros de la comunidad.');
    expect(texto).toContain('Calle Mayor 1, Madrid');
    expect(texto).toContain('LinkedIn');
    expect(texto).toContain('Encuentro próximo');
    expect(texto).toContain('Encuentro viejo');
    const enlaces = [...fixture.nativeElement.querySelectorAll('a.ev')].map((a) =>
      (a as HTMLAnchorElement).getAttribute('href'),
    );
    expect(enlaces).toEqual(['/acme/proximo', '/acme/viejo']);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('en tema claro tampoco tiene violaciones de accesibilidad', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const fixture = abrir();
    fixture.detectChanges();
    responder([evento('a', 'A')], []);
    await avanzar(fixture);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('sin eventos enseña el estado vacío de cada sección', async () => {
    const fixture = abrir();
    fixture.detectChanges();
    responder([], []);
    await avanzar(fixture);

    const texto: string = fixture.nativeElement.textContent;
    expect(texto).toContain('Ahora mismo no hay eventos próximos.');
    expect(texto).toContain('Todavía no hay eventos pasados.');
  });

  it('«Ver más» pide la siguiente página con el offset de lo ya cargado', async () => {
    const fixture = abrir();
    fixture.detectChanges();
    responder([], [evento('p1', 'Pasado 1')], 2);
    await avanzar(fixture);

    const boton = fixture.nativeElement.querySelector('app-button button') as HTMLButtonElement;
    boton.click();
    await avanzar(fixture);
    http
      .expectOne((p) => p.url.includes('when=past') && p.url.includes('offset=1'))
      .flush({ items: [evento('p2', 'Pasado 2')], total: 2 });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Pasado 2');
    expect(fixture.nativeElement.querySelector('app-button')).toBeNull();
  });

  it('un fallo que no es 404 no dice «sin página pública»: enseña el aviso temporal', async () => {
    const fixture = abrir();
    fixture.detectChanges();
    http
      .expectOne('/api/v1/public/organizations/acme')
      .flush({ detail: 'x' }, { status: 500, statusText: 'Server Error' });
    http
      .match((p) => p.url.includes('/events'))
      .forEach((p) => p.flush({ detail: 'x' }, { status: 500, statusText: 'Server Error' }));
    await avanzar(fixture);

    const texto: string = fixture.nativeElement.textContent;
    expect(texto).toContain('No hemos podido comprobar ese enlace');
    expect(texto).not.toContain('no tiene página pública');
  });

  it('con la página desactivada (404) enseña el aviso con enlace a /eventos', async () => {
    const fixture = abrir();
    fixture.detectChanges();
    http
      .expectOne('/api/v1/public/organizations/acme')
      .flush({ detail: 'x' }, { status: 404, statusText: 'Not Found' });
    http
      .match((p) => p.url.includes('/events'))
      .forEach((p) => p.flush({ detail: 'x' }, { status: 404, statusText: 'Not Found' }));
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('no tiene página pública');
    const enlace = fixture.nativeElement.querySelector('a') as HTMLAnchorElement;
    expect(enlace.getAttribute('href')).toBe('/eventos');
  });
});
