import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import type { ReceiptDraft } from './accounting-types';
import { ReceiptReviewForm } from './receipt-review-form';

const CONFIRM = '/api/v1/accounting/expense-drafts/d1/confirm';
const DISCARD = '/api/v1/accounting/expense-drafts/d1/discard';

function draft(sobreescritura: Partial<ReceiptDraft> = {}): ReceiptDraft {
  return {
    id: 'd1',
    event_id: 'e1',
    status: 'pending_review',
    error_code: null,
    ocr_provider: 'openai/gpt-4o-mini',
    // `.pdf` y sin rasterizada: así no hay previsualización que descargar en
    // los tests que no van de eso.
    receipt_object_key: 'orgs/o1/accounting-receipts/abc.pdf',
    rasterized_object_key: null,
    extracted_fields: {
      provider_name: 'Catering SL',
      expense_date: '2026-09-05',
      base_cents: 10_000,
      vat_cents: 2_100,
      total_cents: 12_100,
      currency: 'EUR',
    },
    field_confidence: {
      provider_name: 'alta',
      expense_date: 'alta',
      base_cents: 'alta',
      vat_cents: 'media',
      total_cents: 'alta',
      currency: 'alta',
    },
    attempts: 1,
    confirmed_expense_id: null,
    created_at: '2026-09-05T10:00:00Z',
    ...sobreescritura,
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function montar(
  borrador: ReceiptDraft = draft(),
): Promise<ComponentFixture<ReceiptReviewForm>> {
  const fixture = TestBed.createComponent(ReceiptReviewForm);
  fixture.componentRef.setInput('draft', borrador);
  fixture.componentRef.setInput('partidas', [{ id: 'p1', name: 'Catering' }]);
  await avanzar(fixture);
  return fixture;
}

function escribir(fixture: ComponentFixture<ReceiptReviewForm>, sufijo: string, valor: string) {
  const campo = fixture.nativeElement.querySelector(`#draft-d1-${sufijo}`) as HTMLInputElement;
  campo.value = valor;
  campo.dispatchEvent(new Event('input'));
}

function botonPorTexto(fixture: ComponentFixture<unknown>, texto: string): HTMLButtonElement {
  const botones = Array.from(
    fixture.nativeElement.querySelectorAll('button'),
  ) as HTMLButtonElement[];
  const encontrado = botones.find((boton) => boton.textContent?.includes(texto));
  expect(encontrado, `No hay ningún botón con «${texto}»`).toBeTruthy();
  return encontrado!;
}

async function enviar(fixture: ComponentFixture<ReceiptReviewForm>): Promise<void> {
  const formulario = fixture.nativeElement.querySelector('form') as HTMLFormElement;
  formulario.dispatchEvent(new Event('submit'));
  await avanzar(fixture);
}

describe('ReceiptReviewForm', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    // jsdom no implementa `showModal`/`close` de `<dialog>`: dobles mínimos
    // que solo reflejan el atributo `open`, igual que en `event-payments`.
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      };
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      };
    } else {
      vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (
        this: HTMLDialogElement,
      ) {
        this.setAttribute('open', '');
      });
      vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (
        this: HTMLDialogElement,
      ) {
        this.removeAttribute('open');
      });
    }

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

  it('rellena los campos con lo extraído y confirma creando el gasto', async () => {
    const fixture = await montar();
    let aviso: string | null = null;
    fixture.componentInstance.confirmado.subscribe((mensaje) => (aviso = mensaje));

    const proveedor = fixture.nativeElement.querySelector('#draft-d1-proveedor');
    expect((proveedor as HTMLInputElement).value).toBe('Catering SL');

    await enviar(fixture);
    const peticion = http.expectOne(CONFIRM);
    expect(peticion.request.body.base_cents).toBe(10_000);
    expect(peticion.request.body.vat_cents).toBe(2_100);
    expect(peticion.request.body.total_cents).toBe(12_100);
    expect(peticion.request.body.confirmar_importe_alto).toBe(false);
    peticion.flush({ id: 'g1' });
    await avanzar(fixture);

    expect(aviso).not.toBeNull();
  });

  it('un total que no es base más IVA bloquea el envío en cliente', async () => {
    const fixture = await montar();
    escribir(fixture, 'total', '999');
    await enviar(fixture);

    expect(fixture.nativeElement.textContent).toContain(
      'El total tiene que ser la base más el IVA',
    );
    http.expectNone(CONFIRM);
  });

  it('exento de IVA permite que el total sea solo la base', async () => {
    const fixture = await montar();
    const exento = fixture.nativeElement.querySelector('#draft-d1-exento') as HTMLInputElement;
    exento.checked = true;
    exento.dispatchEvent(new Event('change'));
    await avanzar(fixture);
    escribir(fixture, 'total', '100.00');
    await enviar(fixture);

    const peticion = http.expectOne(CONFIRM);
    expect(peticion.request.body.vat_cents).toBeNull();
    expect(peticion.request.body.total_cents).toBe(10_000);
    peticion.flush({ id: 'g1' });
    await avanzar(fixture);
  });

  it('un importe negativo no se envía', async () => {
    const fixture = await montar();
    escribir(fixture, 'base', '-10');
    escribir(fixture, 'total', '-10');
    await enviar(fixture);

    expect(fixture.nativeElement.textContent).toContain('mayor o igual que 0');
    http.expectNone(CONFIRM);
  });

  it('sin proveedor y sin fecha no se envía', async () => {
    const fixture = await montar();
    escribir(fixture, 'proveedor', '');
    await enviar(fixture);
    expect(fixture.nativeElement.textContent).toContain('Escribe el nombre del proveedor');
    http.expectNone(CONFIRM);

    escribir(fixture, 'proveedor', 'Catering SL');
    escribir(fixture, 'fecha', '');
    await enviar(fixture);
    expect(fixture.nativeElement.textContent).toContain('Indica la fecha del gasto');
    http.expectNone(CONFIRM);
  });

  it('un campo de confianza baja se presenta como «no extraído», no como un hueco vacío', async () => {
    const fixture = await montar(
      draft({
        extracted_fields: {
          provider_name: null,
          expense_date: '2026-09-05',
          base_cents: 10_000,
          vat_cents: 2_100,
          total_cents: 12_100,
          currency: 'EUR',
        },
        field_confidence: {
          provider_name: 'baja',
          expense_date: 'alta',
          base_cents: 'alta',
          vat_cents: 'media',
          total_cents: 'alta',
          currency: 'alta',
        },
      }),
    );

    const pista = fixture.nativeElement.querySelector('#draft-d1-proveedor-pista') as HTMLElement;
    expect(pista.textContent).toContain('No extraído');
    const proveedor = fixture.nativeElement.querySelector(
      '#draft-d1-proveedor',
    ) as HTMLInputElement;
    // La pista está enlazada al campo: quien usa lector de pantalla la oye.
    expect(proveedor.getAttribute('aria-describedby')).toBe('draft-d1-proveedor-pista');
  });

  it('la confianza se muestra como nivel, nunca como porcentaje', async () => {
    const fixture = await montar();
    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Confianza alta');
    expect(texto).toContain('Confianza media');
    expect(texto).not.toContain('%');
  });

  it('un 422 del backend se muestra tal cual aunque la validación de cliente lo dejara pasar', async () => {
    const fixture = await montar();
    await enviar(fixture);

    http
      .expectOne(CONFIRM)
      .flush(
        { detail: 'Esa partida de presupuesto no existe en el evento de este borrador.' },
        { status: 422, statusText: 'Unprocessable Entity' },
      );
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain(
      'Esa partida de presupuesto no existe en el evento de este borrador.',
    );
  });

  it('un importe por encima del techo pide segunda confirmación y reenvía con el flag', async () => {
    const fixture = await montar();
    escribir(fixture, 'base', '2000');
    escribir(fixture, 'iva', '0');
    escribir(fixture, 'total', '2000');
    await enviar(fixture);

    http.expectOne(CONFIRM).flush(
      {
        detail:
          'El importe supera el techo de confirmación automática: vuelve a enviarlo con «confirmar_importe_alto» si es correcto.',
      },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await avanzar(fixture);

    // El importe se enseña en grande antes de insistir.
    expect(fixture.nativeElement.querySelector('.importe-alto')?.textContent).toContain('2000.00');

    botonPorTexto(fixture, 'Sí, dar de alta este gasto').click();
    await avanzar(fixture);

    const segunda = http.expectOne(CONFIRM);
    expect(segunda.request.body.confirmar_importe_alto).toBe(true);
    expect(segunda.request.body.total_cents).toBe(200_000);
    segunda.flush({ id: 'g1' });
    await avanzar(fixture);
  });

  it('el techo se reconoce por el «code» del problem+json, no por el texto', async () => {
    const fixture = await montar();
    escribir(fixture, 'base', '2000');
    escribir(fixture, 'iva', '0');
    escribir(fixture, 'total', '2000');
    await enviar(fixture);

    // Mismo rechazo con el copy reescrito: el `code` es lo que manda.
    http.expectOne(CONFIRM).flush(
      {
        detail: 'Ese importe es demasiado grande para darlo de alta sin revisar.',
        code: 'importe_sobre_techo',
      },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('.importe-alto')?.textContent).toContain('2000.00');
  });

  it('descartar exige confirmación en un diálogo y cancelar no llama al API', async () => {
    const fixture = await montar();
    botonPorTexto(fixture, 'Descartar').click();
    await avanzar(fixture);

    const dialogo = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    expect(dialogo.hasAttribute('open')).toBe(true);
    expect(dialogo.textContent).toContain('No se puede deshacer');
    http.expectNone(DISCARD);

    botonPorTexto(fixture, 'Cancelar').click();
    await avanzar(fixture);
    expect(dialogo.hasAttribute('open')).toBe(false);
    http.expectNone(DISCARD);
  });

  it('confirmar el descarte borra el justificante y lo avisa', async () => {
    const fixture = await montar();
    let aviso: string | null = null;
    fixture.componentInstance.descartado.subscribe((mensaje) => (aviso = mensaje));

    botonPorTexto(fixture, 'Descartar').click();
    await avanzar(fixture);
    botonPorTexto(fixture, 'Sí, descartar y borrar el fichero').click();
    await avanzar(fixture);

    http.expectOne(DISCARD).flush({ id: 'd1', status: 'discarded' });
    await avanzar(fixture);

    expect(aviso).not.toBeNull();
  });

  it('la previsualización libera su object URL al destruirse', async () => {
    const crear = vi.fn(() => 'blob:previsualizacion');
    const liberar = vi.fn();
    vi.spyOn(URL, 'createObjectURL').mockImplementation(crear);
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(liberar);

    const fixture = await montar(
      draft({ rasterized_object_key: 'orgs/o1/accounting-receipts/abc.png' }),
    );
    http
      .expectOne('/api/v1/accounting/receipts/orgs/o1/accounting-receipts/abc.png')
      .flush(new Blob(['x']));
    await avanzar(fixture);

    expect(crear).toHaveBeenCalled();
    const imagen = fixture.nativeElement.querySelector('img') as HTMLImageElement;
    expect(imagen.getAttribute('src')).toContain('blob:previsualizacion');

    fixture.destroy();
    expect(liberar).toHaveBeenCalledWith('blob:previsualizacion');
  });

  it('no tiene violaciones de accesibilidad, ni revisando ni con el diálogo de descarte abierto', async () => {
    const fixture = await montar();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);

    botonPorTexto(fixture, 'Descartar').click();
    await avanzar(fixture);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('se puede recorrer con teclado hasta confirmar, y el diálogo devuelve el foco al salir', async () => {
    const fixture = await montar();

    // Ningún control del flujo está fuera del orden de tabulación ni inerte.
    const enfocables = Array.from(
      fixture.nativeElement.querySelectorAll('input:not([disabled]), button:not([disabled])'),
    ) as HTMLElement[];
    for (const elemento of enfocables) {
      expect(elemento.tabIndex).toBeGreaterThanOrEqual(0);
    }

    const descartar = botonPorTexto(fixture, 'Descartar');
    descartar.focus();
    expect(document.activeElement).toBe(descartar);

    descartar.click();
    await avanzar(fixture);
    const cancelar = botonPorTexto(fixture, 'Cancelar');
    cancelar.focus();
    expect(document.activeElement).toBe(cancelar);

    // Salir del diálogo devuelve el foco a donde estaba: sin trampa.
    cancelar.click();
    await avanzar(fixture);
    expect(document.activeElement).toBe(descartar);

    botonPorTexto(fixture, 'Confirmar y dar de alta el gasto').click();
    await avanzar(fixture);
    http.expectOne(CONFIRM).flush({ id: 'g1' });
    await avanzar(fixture);
  });

  it('el foco va al primer campo cuando el borrador acaba de quedar listo', async () => {
    const fixture = await montar();
    fixture.componentRef.setInput('enfocar', true);
    await avanzar(fixture);

    expect(document.activeElement).toBe(fixture.nativeElement.querySelector('#draft-d1-proveedor'));
  });
});
