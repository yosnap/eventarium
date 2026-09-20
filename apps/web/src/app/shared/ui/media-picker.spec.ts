import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { MediaElegida, MediaPicker } from './media-picker';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('MediaPicker', () => {
  let fixture: ComponentFixture<MediaPicker>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        MediaPicker,
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
    fixture = TestBed.createComponent(MediaPicker);
    fixture.componentRef.setInput('etiqueta', 'Logotipo');
    fixture.componentRef.setInput('aceptados', 'image/png');
    fixture.componentRef.setInput('kind', 'branding');
    fixture.componentRef.setInput('url', 'https://ejemplo.test/logo.png');
  });

  afterEach(() => {
    http.verify();
  });

  it('con imagen ya elegida, muestra "Cambiar" pero no "Quitar"', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('Cambiar');
    // Sin "Quitar": ningún endpoint de asignación admite un `media_id: null`
    // que lo justifique — un botón así sería puramente cosmético y la
    // imagen reaparecería al recargar (hallazgo de code-review).
    expect(raiz.textContent).not.toContain('Quitar');
  });

  it('elegir un medio (vía MediaFields) actualiza url/mediaId y lo emite', async () => {
    fixture.componentRef.setInput('url', null);
    await avanzar(fixture);

    let emitido: MediaElegida | undefined;
    fixture.componentInstance.mediaElegido.subscribe((valor) => (emitido = valor));

    const raiz = fixture.nativeElement as HTMLElement;
    const campoFichero = raiz.querySelector('input[type="file"]') as HTMLInputElement;
    const fichero = new File([new Uint8Array([1])], 'logo.png', { type: 'image/png' });
    Object.defineProperty(campoFichero, 'files', { value: [fichero] });
    campoFichero.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    http
      .expectOne('/api/v1/organizations/me/media')
      .flush({ id: 'media-1', url: 'https://cdn.test/logo.webp' });
    await avanzar(fixture);

    expect(fixture.componentInstance.url()).toBe('https://cdn.test/logo.webp');
    expect(fixture.componentInstance.mediaId()).toBe('media-1');
    expect(emitido).toEqual({ id: 'media-1', url: 'https://cdn.test/logo.webp' });
  });

  it('revertir() deshace la última elección — para cuando el consumidor no logra asignarla', async () => {
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    (raiz.querySelector('button') as HTMLButtonElement).click(); // "Cambiar" abre el diálogo
    await avanzar(fixture);
    const campoFichero = raiz.querySelector('input[type="file"]') as HTMLInputElement;
    const fichero = new File([new Uint8Array([1])], 'nuevo.png', { type: 'image/png' });
    Object.defineProperty(campoFichero, 'files', { value: [fichero] });
    campoFichero.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    http
      .expectOne('/api/v1/organizations/me/media')
      .flush({ id: 'media-nuevo', url: 'https://cdn.test/nuevo.webp' });
    await avanzar(fixture);
    expect(fixture.componentInstance.url()).toBe('https://cdn.test/nuevo.webp');

    // El consumidor llama a esto si la asignación real (su propio PUT) falla.
    fixture.componentInstance.revertir();
    expect(fixture.componentInstance.url()).toBe('https://ejemplo.test/logo.png');
    expect(fixture.componentInstance.mediaId()).toBeNull();
  });
});
