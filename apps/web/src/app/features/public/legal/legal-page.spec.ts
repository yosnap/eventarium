import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { LegalPage } from './legal-page';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('LegalPage', () => {
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
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    document.documentElement.removeAttribute('data-theme');
  });

  it('muestra el contenido en tema claro sin violaciones de accesibilidad', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const fixture = TestBed.createComponent(LegalPage);
    fixture.componentRef.setInput('page', 'privacidad');
    fixture.detectChanges();

    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/legal/privacidad')
      .flush({ content: '**Responsable**\n\nAcme SL trata tus datos.' });
    await avanzar(fixture);
    await avanzar(fixture);

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra el contenido de la plantilla y pide la ruta correcta, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(LegalPage);
    fixture.componentRef.setInput('page', 'privacidad');
    fixture.detectChanges();

    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/legal/privacidad')
      .flush({ content: '**Responsable**\n\nAcme SL trata tus datos.' });
    await avanzar(fixture);
    // Segundo ciclo: `afterNextRender` sanea el Markdown de forma asíncrona
    // tras el primer render.
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('Responsable');
    expect(raiz.textContent).toContain('Acme SL trata tus datos.');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('un <script> guardado como contenido legal no aparece ejecutable en el DOM servido', async () => {
    const fixture = TestBed.createComponent(LegalPage);
    fixture.componentRef.setInput('page', 'aviso-legal');
    fixture.detectChanges();

    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/legal/aviso-legal')
      .flush({ content: 'Texto normal.\n\n<script>alert(1)</script>' });
    await avanzar(fixture);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    // Ni como etiqueta real en el DOM (que el navegador ejecutaría), ni como
    // texto: el contenido debe llegar saneado antes de mostrarse.
    expect(raiz.querySelector('script')).toBeNull();
    expect(raiz.innerHTML).not.toContain('<script');
    expect(raiz.textContent).toContain('Texto normal.');
  });

  it('sanea el markdown aunque el contenido llegue después del primer render (navegación cliente-cliente)', async () => {
    // Regresión del hallazgo #3 del code-review: un `afterNextRender` de una
    // sola vez podía consumirse antes de que `cargar()` (asíncrono) resolviera
    // en una navegación SPA, dejando la página en texto plano para siempre.
    // El `effect()` debe reaccionar cuando el contenido llega, no solo una vez.
    const fixture = TestBed.createComponent(LegalPage);
    fixture.componentRef.setInput('page', 'cookies');
    fixture.detectChanges(); // primer render: la petición HTTP sigue en vuelo.

    expect(fixture.nativeElement.querySelector('.contenido')).toBeNull();

    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/legal/cookies')
      .flush({ content: '**Cookies** técnicas y de análisis.' });
    await avanzar(fixture);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('.contenido')).not.toBeNull();
    expect(raiz.textContent).toContain('Cookies');
  });

  it('pide la ruta correcta para cada página pública', async () => {
    const rutas: Record<string, string> = {
      'aviso-legal': 'aviso-legal',
      privacidad: 'privacidad',
      cookies: 'cookies',
      'condiciones-de-inscripcion': 'condiciones-de-inscripcion',
    };

    for (const [pagina, ruta] of Object.entries(rutas)) {
      const fixture = TestBed.createComponent(LegalPage);
      fixture.componentRef.setInput('page', pagina);
      fixture.detectChanges();
      http
        .expectOne((peticion) => peticion.url === `/api/v1/public/legal/${ruta}`)
        .flush({
          content: 'Contenido.',
        });
      await avanzar(fixture);
    }
  });
});
