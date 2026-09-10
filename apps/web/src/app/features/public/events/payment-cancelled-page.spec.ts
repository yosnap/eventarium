import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import { PaymentCancelledPage } from './payment-cancelled-page';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function rutaCon(parametros: Record<string, string>) {
  return { snapshot: { queryParamMap: convertToParamMap(parametros) } };
}

describe('PaymentCancelledPage', () => {
  function configurar(ruta: unknown) {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: ruta },
      ],
    }).compileComponents();
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('muestra el aviso de cancelación en tema claro sin violaciones de accesibilidad', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    configurar(rutaCon({ slug: 'iawic-2026' }));

    const fixture = TestBed.createComponent(PaymentCancelledPage);
    await fixture.whenStable();

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra el aviso de cancelación y un enlace de vuelta al evento, sin violaciones de accesibilidad', async () => {
    configurar(rutaCon({ slug: 'iawic-2026' }));

    const fixture = TestBed.createComponent(PaymentCancelledPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Pago cancelado');
    const enlace = fixture.nativeElement.querySelector('a');
    expect(enlace?.getAttribute('href')).toContain('/eventos/iawic-2026');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('sin `slug` en la URL no muestra el enlace de vuelta', async () => {
    configurar(rutaCon({}));

    const fixture = TestBed.createComponent(PaymentCancelledPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('a')).toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
