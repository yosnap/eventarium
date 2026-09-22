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

  it('sin arrastrar nada, "Guardar como nueva" y "Sobrescribir original" están deshabilitados', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    expect(botonPorTexto(raiz, 'Guardar como nueva').disabled).toBe(true);
    expect(botonPorTexto(raiz, 'Sobrescribir original').disabled).toBe(true);
  });

  it('arrastrar sobre la imagen habilita confirmar y "Guardar como nueva" emite sobrescribir:false', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    let emitido: { blob: Blob; sobrescribir: boolean } | undefined;
    fixture.componentInstance.confirmado.subscribe((valor) => (emitido = valor));

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    fixture.detectChanges();

    const botonConfirmar = botonPorTexto(raiz, 'Guardar como nueva');
    expect(botonConfirmar.disabled).toBe(false);
    botonConfirmar.click();
    await avanzar(fixture);

    expect(emitido?.blob).toBeInstanceOf(Blob);
    expect(emitido?.sobrescribir).toBe(false);
  });

  it('el spinner sigue visible mientras el padre reporta confirmando=true tras el emit síncrono', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    fixture.detectChanges();

    botonPorTexto(raiz, 'Guardar como nueva').click();
    await avanzar(fixture);

    // `confirmado.emit()` ya ha vuelto (síncrono) y `generando()` ya es
    // `false` — pero la subida real en el padre sigue en curso, reflejada
    // aquí como el input `confirmando`. El botón debe seguir mostrando el
    // spinner (aria-busy), no solo quedar deshabilitado en silencio.
    fixture.componentRef.setInput('confirmando', true);
    await avanzar(fixture);

    const boton = botonPorTexto(raiz, 'Guardar como nueva');
    expect(boton.disabled).toBe(true);
    expect(boton.getAttribute('aria-busy')).toBe('true');
  });

  it('"Sobrescribir original" emite sobrescribir:true', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    let emitido: { blob: Blob; sobrescribir: boolean } | undefined;
    fixture.componentInstance.confirmado.subscribe((valor) => (emitido = valor));

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    fixture.detectChanges();

    botonPorTexto(raiz, 'Sobrescribir original').click();
    await avanzar(fixture);

    expect(emitido?.sobrescribir).toBe(true);
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

  it('elegir una proporción fija dibuja de inmediato una selección centrada, sin arrastrar', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    expect(raiz.querySelector('.seleccion')).toBeNull();
    botonPorTexto(raiz, '16:9').click();
    fixture.detectChanges();

    const seleccion = raiz.querySelector('.seleccion') as HTMLDivElement;
    expect(seleccion).not.toBeNull();
    // Centrada: el hueco a cada lado (izquierda vs derecha, arriba vs abajo)
    // debe ser igual.
    const izquierda = parseFloat(seleccion.style.left);
    const derecha = 100 - izquierda - parseFloat(seleccion.style.width);
    expect(izquierda).toBeCloseTo(derecha, 5);
    expect(botonPorTexto(raiz, 'Guardar como nueva').disabled).toBe(false);
  });

  it('elegir "Libre" no borra una selección ya dibujada', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    botonPorTexto(raiz, '16:9').click();
    fixture.detectChanges();
    expect(raiz.querySelector('.seleccion')).not.toBeNull();

    botonPorTexto(raiz, 'Libre').click();
    fixture.detectChanges();

    expect(raiz.querySelector('.seleccion')).not.toBeNull();
  });

  it('arrastrar desde dentro de la selección la mueve, sin cambiar su tamaño', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointerup', { clientX: 120, clientY: 60 }));
    fixture.detectChanges();

    // Rectángulo inicial en porcentaje: left 10, top 10, width 50, height 50.
    // Pulsar dentro (60,30px → 30%,30%) y arrastrar hasta (80,50px → 40%,50%)
    // debe desplazar el rectángulo entero +10%,+20% sin tocar su tamaño.
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 60, clientY: 30, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 80, clientY: 50, buttons: 1 }));
    fixture.detectChanges();

    const seleccion = raiz.querySelector('.seleccion') as HTMLDivElement;
    expect(parseFloat(seleccion.style.left)).toBeCloseTo(20, 5);
    expect(parseFloat(seleccion.style.top)).toBeCloseTo(30, 5);
    expect(parseFloat(seleccion.style.width)).toBeCloseTo(50, 5);
    expect(parseFloat(seleccion.style.height)).toBeCloseTo(50, 5);
  });

  it('arrastrar desde un tirador de esquina la redimensiona, sin mover la esquina opuesta', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointerup', { clientX: 120, clientY: 60 }));
    fixture.detectChanges();

    const tirador = raiz.querySelector('.manejador-se') as HTMLSpanElement;
    tirador.dispatchEvent(
      new PointerEvent('pointerdown', { clientX: 120, clientY: 60, buttons: 1, bubbles: true }),
    );
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 160, clientY: 80, buttons: 1 }));
    fixture.detectChanges();

    const seleccion = raiz.querySelector('.seleccion') as HTMLDivElement;
    // La esquina opuesta (superior izquierda, 20,10 en px) no se ha movido.
    expect(parseFloat(seleccion.style.left)).toBeCloseTo(10, 5);
    expect(parseFloat(seleccion.style.top)).toBeCloseTo(10, 5);
    expect(parseFloat(seleccion.style.width)).toBeCloseTo(70, 5);
    expect(parseFloat(seleccion.style.height)).toBeCloseTo(70, 5);
  });

  it('redimensionar hacia fuera nunca deja la selección salirse de los bordes de la imagen', async () => {
    await avanzar(fixture);
    await esperarCarga(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    mockearCajaDeLaImagen(raiz);

    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.dispatchEvent(new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 120, clientY: 60, buttons: 1 }));
    lienzo.dispatchEvent(new PointerEvent('pointerup', { clientX: 120, clientY: 60 }));
    fixture.detectChanges();

    const tirador = raiz.querySelector('.manejador-se') as HTMLSpanElement;
    tirador.dispatchEvent(
      new PointerEvent('pointerdown', { clientX: 120, clientY: 60, buttons: 1, bubbles: true }),
    );
    // Arrastra muy por fuera de la imagen (el lienzo mockeado mide 200×100px).
    lienzo.dispatchEvent(new PointerEvent('pointermove', { clientX: 5000, clientY: 5000, buttons: 1 }));
    fixture.detectChanges();

    const seleccion = raiz.querySelector('.seleccion') as HTMLDivElement;
    const izquierda = parseFloat(seleccion.style.left);
    const arriba = parseFloat(seleccion.style.top);
    const ancho = parseFloat(seleccion.style.width);
    const alto = parseFloat(seleccion.style.height);
    expect(izquierda).toBeGreaterThanOrEqual(0);
    expect(arriba).toBeGreaterThanOrEqual(0);
    expect(izquierda + ancho).toBeLessThanOrEqual(100.0001);
    expect(arriba + alto).toBeLessThanOrEqual(100.0001);
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
