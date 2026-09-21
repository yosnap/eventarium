import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { MediaCropEditor } from './media-crop-editor';

/** jsdom no decodifica imágenes reales ni soporta `<canvas>` 2D: se sustituye
 * `Image` por una versión síncrona (resuelve `onload` en un microtask) y se
 * simulan `getContext`/`toDataURL`/`toBlob` — el objetivo de este spec es la
 * lógica de arrastre/proporción/emisión, no el resultado real de píxeles. */
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

/** Espera a que termine la carga asíncrona de la imagen (microtasks del
 * `effect` del constructor), sondeando el signal `cargando` protegido. */
async function esperarCarga(fixture: ComponentFixture<MediaCropEditor>): Promise<void> {
  const instancia = fixture.componentInstance as unknown as { cargando: () => boolean };
  for (let intento = 0; intento < 20; intento++) {
    await Promise.resolve();
    fixture.detectChanges();
    if (!instancia.cargando()) {
      return;
    }
  }
  throw new Error('La imagen no terminó de cargar en el test.');
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

describe('MediaCropEditor', () => {
  let fixture: ComponentFixture<MediaCropEditor>;

  beforeEach(() => {
    // jsdom no implementa la Pointer Capture API.
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
        MediaCropEditor,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(MediaCropEditor);
    fixture.componentRef.setInput('url', 'https://ejemplo.test/foto.jpg');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function mockearCajaDeLaImagen(raiz: HTMLElement): void {
    const imagen = raiz.querySelector('img') as HTMLImageElement;
    imagen.getBoundingClientRect = () => ({ left: 0, top: 0, width: 200, height: 100 }) as DOMRect;
  }

  it('sin arrastrar nada, "Confirmar recorte" está deshabilitado', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    expect(botonPorTexto(raiz, 'Confirmar recorte').disabled).toBe(true);
  });

  it('arrastrar sobre la imagen habilita confirmar y emite un Blob', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    let emitido: Blob | undefined;
    fixture.componentInstance.confirmado.subscribe((valor) => (emitido = valor));

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    fixture.detectChanges();

    const botonConfirmar = botonPorTexto(raiz, 'Confirmar recorte');
    expect(botonConfirmar.disabled).toBe(false);
    botonConfirmar.click();
    await avanzar(fixture);

    expect(emitido).toBeInstanceOf(Blob);
  });

  it('con proporción 1:1, el rectángulo real en píxeles sale cuadrado aunque la imagen mostrada no lo sea', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    botonPorTexto(raiz, '1:1').click();
    fixture.detectChanges();

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 0, clientY: 0, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 80, clientY: 40, buttons: 1 }));
    fixture.detectChanges();

    const seleccion = raiz.querySelector('.seleccion') as HTMLDivElement;
    // La imagen simulada mide 200×100 (2:1). Un rectángulo real 1:1 sobre
    // ella, expresado en fracciones, NO es cuadrado en pantalla — hay que
    // volver a multiplicar por las dimensiones reales para comprobarlo.
    const anchoPx = (parseFloat(seleccion.style.width) / 100) * 200;
    const altoPx = (parseFloat(seleccion.style.height) / 100) * 100;
    expect(anchoPx).toBeCloseTo(altoPx, 5);
  });

  it('voltear horizontal marca el botón como activo', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;

    const botonVoltear = raiz.querySelector(
      'button[aria-label="Voltear horizontal"]',
    ) as HTMLButtonElement;
    expect(botonVoltear.classList.contains('activo')).toBe(false);
    botonVoltear.click();
    fixture.detectChanges();
    expect(botonVoltear.classList.contains('activo')).toBe(true);
  });

  it('"Cancelar" emite `cancelado` sin ningún rectángulo', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    let canceladoEmitido = false;
    fixture.componentInstance.cancelado.subscribe(() => (canceladoEmitido = true));

    const raiz = fixture.nativeElement as HTMLElement;
    botonPorTexto(raiz, 'Cancelar').click();

    expect(canceladoEmitido).toBe(true);
  });
});
