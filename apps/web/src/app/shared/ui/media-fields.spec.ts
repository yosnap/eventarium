import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { MediaElegida, MediaFields } from './media-fields';

const MEDIA_URL = '/api/v1/organizations/me/media';
const CARPETAS_URL = '/api/v1/organizations/me/media-folders';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('MediaFields', () => {
  let fixture: ComponentFixture<MediaFields>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        MediaFields,
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
    fixture = TestBed.createComponent(MediaFields);
    fixture.componentRef.setInput('aceptados', 'image/png');
    fixture.componentRef.setInput('kind', 'branding');
  });

  afterEach(() => {
    http.verify();
  });

  it('con permitirUrl por defecto, muestra las 3 pestañas', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelectorAll('[role="tab"]').length).toBe(3);
  });

  it('con permitirUrl=false, oculta la pestaña "Desde URL"', async () => {
    fixture.componentRef.setInput('permitirUrl', false);
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).not.toContain('Desde URL');
    expect(raiz.querySelectorAll('[role="tab"]').length).toBe(2);
  });

  it('elegir un fichero lo sube a la biblioteca de organización y emite el media_id', async () => {
    await avanzar(fixture);
    let emitido: MediaElegida | undefined;
    fixture.componentInstance.mediaElegido.subscribe((valor) => (emitido = valor));

    const raiz = fixture.nativeElement as HTMLElement;
    const campoFichero = raiz.querySelector('input[type="file"]') as HTMLInputElement;
    const fichero = new File([new Uint8Array([1])], 'logo.png', { type: 'image/png' });
    Object.defineProperty(campoFichero, 'files', { value: [fichero] });
    campoFichero.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const subida = http.expectOne(MEDIA_URL);
    expect(subida.request.method).toBe('POST');
    expect(subida.request.body instanceof FormData).toBe(true);
    expect((subida.request.body as FormData).get('kind')).toBe('branding');
    subida.flush({ id: 'media-1', url: 'https://cdn.test/logo.webp' });
    await avanzar(fixture);

    expect(emitido).toEqual({ id: 'media-1', url: 'https://cdn.test/logo.webp' });
  });

  it('con kind="platform", la subida no lleva el campo kind', async () => {
    fixture.componentRef.setInput('kind', 'platform');
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const campoFichero = raiz.querySelector('input[type="file"]') as HTMLInputElement;
    const fichero = new File([new Uint8Array([1])], 'logo.png', { type: 'image/png' });
    Object.defineProperty(campoFichero, 'files', { value: [fichero] });
    campoFichero.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const subida = http.expectOne('/api/v1/admin/platform/media');
    expect((subida.request.body as FormData).has('kind')).toBe(false);
    subida.flush({ id: 'media-1', url: 'https://cdn.test/logo.webp' });
    await avanzar(fixture);
  });

  it('un fallo en la subida muestra el mensaje del servidor, no bloquea el resto del formulario', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    const campoFichero = raiz.querySelector('input[type="file"]') as HTMLInputElement;
    const fichero = new File([new Uint8Array([1])], 'logo.svg', { type: 'image/svg+xml' });
    Object.defineProperty(campoFichero, 'files', { value: [fichero] });
    campoFichero.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    http
      .expectOne(MEDIA_URL)
      .flush(
        { title: 'Datos no válidos', detail: 'Tipo de fichero no admitido.' },
        { status: 422, statusText: 'Unprocessable Entity' },
      );
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Tipo de fichero no admitido.');
  });

  it('la pestaña Biblioteca pide la página al backend con el kind y pinta los resultados', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    const tabs = Array.from(raiz.querySelectorAll('[role="tab"]')) as HTMLButtonElement[];
    tabs.find((t) => t.textContent?.includes('Biblioteca'))!.click();
    await avanzar(fixture);

    http.expectOne((r) => r.url === CARPETAS_URL).flush([]);
    const peticion = http.expectOne((r) => r.url === MEDIA_URL);
    expect(peticion.request.params.get('kind')).toBe('branding');
    expect(peticion.request.params.get('limit')).toBe('12');
    peticion.flush({
      items: [{ id: 'a', url: 'https://cdn.test/a.png', filename: 'a.png', alt: null }],
      total: 1,
      limit: 12,
      offset: 0,
    });
    await avanzar(fixture);

    expect(raiz.querySelectorAll('.rejilla .item').length).toBe(1);
  });

  it('elegir un ítem de biblioteca emite su media_id sin ninguna petición nueva', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    const tabs = Array.from(raiz.querySelectorAll('[role="tab"]')) as HTMLButtonElement[];
    tabs.find((t) => t.textContent?.includes('Biblioteca'))!.click();
    await avanzar(fixture);
    http.expectOne((r) => r.url === CARPETAS_URL).flush([]);
    http.expectOne((r) => r.url === MEDIA_URL).flush({
      items: [{ id: 'a', url: 'https://cdn.test/a.png', filename: 'a.png', alt: null }],
      total: 1,
      limit: 12,
      offset: 0,
    });
    await avanzar(fixture);

    let emitido: MediaElegida | undefined;
    fixture.componentInstance.mediaElegido.subscribe((valor) => (emitido = valor));
    (raiz.querySelector('.rejilla .item') as HTMLButtonElement).click();

    expect(emitido).toEqual({ id: 'a', url: 'https://cdn.test/a.png' });
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('enviar un ítem a la papelera con 409 muestra qué lo está usando', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    const tabs = Array.from(raiz.querySelectorAll('[role="tab"]')) as HTMLButtonElement[];
    tabs.find((t) => t.textContent?.includes('Biblioteca'))!.click();
    await avanzar(fixture);
    http.expectOne((r) => r.url === CARPETAS_URL).flush([]);
    http.expectOne((r) => r.url === MEDIA_URL).flush({
      items: [{ id: 'a', url: 'https://cdn.test/a.png', filename: 'a.png', alt: null }],
      total: 1,
      limit: 12,
      offset: 0,
    });
    await avanzar(fixture);

    const botonPapelera = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('papelera'),
    ) as HTMLButtonElement;
    botonPapelera.click();
    await avanzar(fixture);

    http.expectOne((r) => r.method === 'DELETE').flush(
      { detail: 'En uso.', used_by: [{ tipo: 'evento', id: 'e1', nombre: 'IA Week 2026' }] },
      { status: 409, statusText: 'Conflict' },
    );
    await avanzar(fixture);

    expect(raiz.textContent).toContain('IA Week 2026');
  });
});
