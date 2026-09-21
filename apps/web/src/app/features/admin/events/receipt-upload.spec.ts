import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { MAXIMO_BYTES_DE_JUSTIFICANTE, ReceiptUpload } from './receipt-upload';

const URL_SUBIDA = '/api/v1/accounting/events/e1/expense-drafts';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function montar(): Promise<ComponentFixture<ReceiptUpload>> {
  const fixture = TestBed.createComponent(ReceiptUpload);
  fixture.componentRef.setInput('eventId', 'e1');
  await avanzar(fixture);
  return fixture;
}

function ficheroDe(nombre: string, tipo: string, bytes = 10): File {
  const fichero = new File([new Uint8Array(bytes)], nombre, { type: tipo });
  // jsdom calcula `size` a partir del contenido: para el caso «demasiado
  // grande» se declara el tamaño en vez de reservar 10 MB de verdad.
  return fichero;
}

function ficheroDeTamano(nombre: string, tipo: string, tamano: number): File {
  const fichero = ficheroDe(nombre, tipo);
  Object.defineProperty(fichero, 'size', { value: tamano });
  return fichero;
}

async function elegir(fixture: ComponentFixture<ReceiptUpload>, fichero: File): Promise<void> {
  const entrada = fixture.nativeElement.querySelector('input[type="file"]') as HTMLInputElement;
  Object.defineProperty(entrada, 'files', { value: [fichero], configurable: true });
  entrada.dispatchEvent(new Event('change'));
  await avanzar(fixture);
}

describe('ReceiptUpload', () => {
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
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  it('acepta las cuatro MIME de documento que acepta el backend', async () => {
    const fixture = await montar();
    const entrada = fixture.nativeElement.querySelector('input[type="file"]') as HTMLInputElement;
    expect(entrada.accept).toBe('image/png,image/jpeg,image/webp,application/pdf');
  });

  it('el campo de fichero está en el orden de tabulación', async () => {
    const fixture = await montar();
    const entrada = fixture.nativeElement.querySelector('input[type="file"]') as HTMLInputElement;
    expect(entrada.tabIndex).toBeGreaterThanOrEqual(0);
    expect(entrada.disabled).toBe(false);
  });

  it('un tipo no permitido se avisa sin llamar al API', async () => {
    const fixture = await montar();
    await elegir(fixture, ficheroDe('hoja.xlsx', 'application/vnd.ms-excel'));

    expect(fixture.nativeElement.textContent).toContain('Ese tipo de fichero no vale');
    http.expectNone(URL_SUBIDA);
  });

  it('un fichero demasiado grande se avisa sin llamar al API', async () => {
    const fixture = await montar();
    await elegir(
      fixture,
      ficheroDeTamano('factura.pdf', 'application/pdf', MAXIMO_BYTES_DE_JUSTIFICANTE + 1),
    );

    expect(fixture.nativeElement.textContent).toContain('supera los 10 MB');
    http.expectNone(URL_SUBIDA);
  });

  it('sube el fichero y emite el borrador recién creado', async () => {
    const fixture = await montar();
    let emitido: { id: string } | null = null;
    fixture.componentInstance.subido.subscribe((draft) => (emitido = draft));

    await elegir(fixture, ficheroDe('ticket.png', 'image/png'));
    const peticion = http.expectOne(URL_SUBIDA);
    expect(peticion.request.method).toBe('POST');
    expect((peticion.request.body as FormData).get('fichero')).toBeInstanceOf(File);
    peticion.flush({ id: 'd1', status: 'pending_extraction' });
    await avanzar(fixture);

    expect(emitido).not.toBeNull();
    expect(emitido!.id).toBe('d1');
  });

  it('un 422 del backend se muestra tal cual, aunque la validación de cortesía lo dejara pasar', async () => {
    // El backend valida los **bytes reales**, no la extensión ni el `type` que
    // declara el navegador: su respuesta manda sobre la comprobación local.
    const fixture = await montar();
    await elegir(fixture, ficheroDe('en-realidad-no-es-png.png', 'image/png'));

    http
      .expectOne(URL_SUBIDA)
      .flush(
        { detail: 'Ese tipo de fichero no está permitido.' },
        { status: 422, statusText: 'Unprocessable Entity' },
      );
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Ese tipo de fichero no está permitido.');
  });

  it('anuncia la subida en curso en una región aria-live', async () => {
    const fixture = await montar();
    await elegir(fixture, ficheroDe('ticket.png', 'image/png'));

    const region = fixture.nativeElement.querySelector('[aria-live="polite"]') as HTMLElement;
    expect(region.textContent).toContain('Subiendo');

    http.expectOne(URL_SUBIDA).flush({ id: 'd1' });
    await avanzar(fixture);
  });

  it('no tiene violaciones de accesibilidad, ni vacío ni subiendo', async () => {
    const fixture = await montar();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);

    await elegir(fixture, ficheroDe('ticket.png', 'image/png'));
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);

    http.expectOne(URL_SUBIDA).flush({ id: 'd1' });
    await avanzar(fixture);
  });
});
