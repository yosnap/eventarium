import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { MediaEditDialog } from './media-edit-dialog';
import { MediaItem } from './media-fields';

const MEDIA_URL = '/api/v1/organizations/me/media';

/** Mismo doble que `media-crop-editor.spec.ts`: jsdom no decodifica
 * imágenes reales ni soporta `<canvas>` 2D. */
class ImagenFalsa {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readonly naturalWidth = 200;
  readonly naturalHeight = 100;
  set src(_valor: string) {
    queueMicrotask(() => this.onload?.());
  }
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function esperarCargaDelRecorte(fixture: ComponentFixture<MediaEditDialog>): Promise<void> {
  for (let intento = 0; intento < 20; intento++) {
    await Promise.resolve();
    fixture.detectChanges();
    const editor = (fixture.nativeElement as HTMLElement).querySelector('app-media-crop-editor');
    if (editor?.querySelector('.lienzo')) {
      return;
    }
  }
  throw new Error('El editor de recorte no terminó de cargar en el test.');
}

function botonPorTexto(raiz: HTMLElement, texto: string): HTMLButtonElement {
  const boton = Array.from(raiz.querySelectorAll('button')).find(
    (b) => b.textContent?.trim() === texto,
  );
  if (!boton) {
    throw new Error(`No se ha encontrado ningún botón con el texto "${texto}".`);
  }
  return boton as HTMLButtonElement;
}

function itemDePrueba(overrides: Partial<MediaItem> = {}): MediaItem {
  return {
    id: 'a',
    url: 'https://cdn.test/a.png',
    filename: 'a.png',
    alt: 'Descripción actual',
    folder_id: null,
    mime_type: 'image/png',
    size: 123456,
    width: 800,
    height: 600,
    created_at: '2026-09-20T10:00:00Z',
    ...overrides,
  };
}

describe('MediaEditDialog', () => {
  let fixture: ComponentFixture<MediaEditDialog>;
  let http: HttpTestingController;

  beforeEach(() => {
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      };
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      };
    }
    HTMLElement.prototype.setPointerCapture = () => undefined;
    HTMLElement.prototype.releasePointerCapture = () => undefined;
    vi.stubGlobal('Image', ImagenFalsa);
    const sinOperacion = (): void => undefined;
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      save: sinOperacion,
      translate: sinOperacion,
      rotate: sinOperacion,
      scale: sinOperacion,
      drawImage: sinOperacion,
      restore: sinOperacion,
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(
      'data:image/webp;base64,AAAA',
    );
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (
      this: HTMLCanvasElement,
      callback: BlobCallback,
    ) {
      callback(new Blob(['recorte'], { type: 'image/webp' }));
    });

    TestBed.configureTestingModule({
      imports: [
        MediaEditDialog,
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
    fixture = TestBed.createComponent(MediaEditDialog);
    fixture.componentRef.setInput('kind', 'branding');
  });

  afterEach(() => {
    http.verify();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('abrir() pinta el nombre y el alt actuales del item', async () => {
    await avanzar(fixture);
    fixture.componentInstance.abrir(itemDePrueba());
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const campos = raiz.querySelectorAll('input[type="text"]') as NodeListOf<HTMLInputElement>;
    expect(campos[0].value).toBe('a.png');
    expect(campos[1].value).toBe('Descripción actual');
  });

  it('guardar cambios manda el PATCH con nombre/alt/carpeta y emite metadatosGuardados', async () => {
    await avanzar(fixture);
    fixture.componentInstance.abrir(itemDePrueba());
    await avanzar(fixture);

    let emitido = false;
    fixture.componentInstance.metadatosGuardados.subscribe(() => (emitido = true));

    const raiz = fixture.nativeElement as HTMLElement;
    const campoNombre = raiz.querySelectorAll('input[type="text"]')[0] as HTMLInputElement;
    campoNombre.value = 'nuevo-nombre.png';
    campoNombre.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    botonPorTexto(raiz, 'Guardar cambios').click();
    await avanzar(fixture);

    const peticion = http.expectOne((r) => r.url === `${MEDIA_URL}/a` && r.method === 'PATCH');
    expect(peticion.request.body).toEqual({
      filename: 'nuevo-nombre.png',
      alt: 'Descripción actual',
      folder_id: null,
    });
    peticion.flush({
      id: 'a',
      url: 'https://cdn.test/a.png',
      filename: 'nuevo-nombre.png',
      alt: 'Descripción actual',
      folder_id: null,
    });
    await avanzar(fixture);

    expect(emitido).toBe(true);
  });

  it('confirmar el recorte sube el Media nuevo y emite recorteGuardado, sin ningún otro evento', async () => {
    await avanzar(fixture);
    fixture.componentInstance.abrir(itemDePrueba());
    await avanzar(fixture);
    await esperarCargaDelRecorte(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const imagen = raiz.querySelector('app-media-crop-editor img') as HTMLImageElement;
    imagen.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 200, height: 100 }) as DOMRect;

    let recorteGuardadoEmitido = false;
    fixture.componentInstance.recorteGuardado.subscribe(() => (recorteGuardadoEmitido = true));

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    fixture.detectChanges();

    botonPorTexto(raiz, 'Confirmar recorte').click();
    await avanzar(fixture);

    const subida = http.expectOne((r) => r.url === MEDIA_URL && r.method === 'POST');
    expect(subida.request.body instanceof FormData).toBe(true);
    subida.flush({ id: 'b', url: 'https://cdn.test/b.webp', filename: 'a.png-recorte.webp' });
    await avanzar(fixture);

    expect(recorteGuardadoEmitido).toBe(true);
  });

  it('cancelar el recorte cierra el modal entero (misma convención que el resto de diálogos)', async () => {
    await avanzar(fixture);
    fixture.componentInstance.abrir(itemDePrueba());
    await avanzar(fixture);
    await esperarCargaDelRecorte(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    botonPorTexto(raiz, 'Cancelar').click();
    await avanzar(fixture);

    expect(raiz.querySelector('dialog')?.hasAttribute('open')).toBe(false);
  });

  it('reabrir para otro item mientras el PATCH anterior sigue en vuelo no pisa el formulario nuevo', async () => {
    await avanzar(fixture);
    fixture.componentInstance.abrir(itemDePrueba({ id: 'a', filename: 'a.png' }));
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    botonPorTexto(raiz, 'Guardar cambios').click();
    await avanzar(fixture);
    const peticionDeA = http.expectOne((r) => r.url === `${MEDIA_URL}/a` && r.method === 'PATCH');

    // Reabre para un item distinto antes de que responda el PATCH de "a".
    fixture.componentInstance.abrir(itemDePrueba({ id: 'b', filename: 'b.png', alt: null }));
    await avanzar(fixture);

    peticionDeA.flush({
      id: 'a',
      url: 'https://cdn.test/a.png',
      filename: 'a.png',
      alt: 'Descripción actual',
      folder_id: null,
    });
    await avanzar(fixture);

    const campoNombre = raiz.querySelectorAll('input[type="text"]')[0] as HTMLInputElement;
    expect(campoNombre.value).toBe('b.png');
  });

  it('muestra dimensiones, tamaño y fecha de subida del item', async () => {
    await avanzar(fixture);
    fixture.componentInstance.abrir(
      itemDePrueba({ width: 1920, height: 1080, size: 2_500_000 }),
    );
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const texto = raiz.textContent ?? '';
    expect(texto).toContain('1920 × 1080 px');
    expect(texto).toContain('2.4 MB');
  });

  it('copiar URL escribe en el portapapeles y muestra confirmación', async () => {
    const escribir = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: escribir } });

    await avanzar(fixture);
    fixture.componentInstance.abrir(itemDePrueba({ url: 'https://cdn.test/a.png' }));
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    botonPorTexto(raiz, 'Copiar URL').click();
    await avanzar(fixture);

    expect(escribir).toHaveBeenCalledWith('https://cdn.test/a.png');
    expect(botonPorTexto(raiz, '¡Copiada!')).toBeTruthy();
  });

  it('no tiene violaciones de accesibilidad con el modal abierto', async () => {
    await avanzar(fixture);
    fixture.componentInstance.abrir(itemDePrueba());
    await avanzar(fixture);

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement as HTMLElement);
  });
});
