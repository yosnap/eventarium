import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { MediaCropEditor, RectanguloDeRecorte } from './media-crop-editor';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function punteroEn(clientX: number, clientY: number): PointerEvent {
  return new PointerEvent('pointermove', { clientX, clientY, buttons: 1 });
}

describe('MediaCropEditor', () => {
  let fixture: ComponentFixture<MediaCropEditor>;

  beforeEach(() => {
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

  it('sin arrastrar nada, "Confirmar recorte" está deshabilitado', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    const botonConfirmar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Confirmar recorte'),
    ) as HTMLButtonElement;
    expect(botonConfirmar.disabled).toBe(true);
  });

  it('arrastrar sobre el lienzo produce un rectángulo normalizado y lo confirma', async () => {
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;
    const lienzo = raiz.querySelector('.lienzo') as HTMLDivElement;
    lienzo.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 200, height: 100 }) as DOMRect;

    let emitido: RectanguloDeRecorte | undefined;
    fixture.componentInstance.confirmado.subscribe((valor) => (emitido = valor));

    lienzo.dispatchEvent(
      new PointerEvent('pointerdown', { clientX: 20, clientY: 10, buttons: 1 }),
    );
    lienzo.dispatchEvent(punteroEn(120, 60));
    await avanzar(fixture);

    const botonConfirmar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Confirmar recorte'),
    ) as HTMLButtonElement;
    expect(botonConfirmar.disabled).toBe(false);
    botonConfirmar.click();

    expect(emitido).toEqual({ x: 0.1, y: 0.1, width: 0.5, height: 0.5 });
  });

  it('"Cancelar" emite `cancelado` sin ningún rectángulo', async () => {
    await avanzar(fixture);
    let canceladoEmitido = false;
    fixture.componentInstance.cancelado.subscribe(() => (canceladoEmitido = true));

    const raiz = fixture.nativeElement as HTMLElement;
    const botonCancelar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Cancelar'),
    ) as HTMLButtonElement;
    botonCancelar.click();

    expect(canceladoEmitido).toBe(true);
  });
});
