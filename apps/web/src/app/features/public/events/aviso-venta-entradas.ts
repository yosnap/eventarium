import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import type { PublicEventDetail } from './event-page.types';
import { formatearFecha } from '../../../shared/text/formatear-fecha';
import { IDIOMA_POR_DEFECTO } from '../../../core/i18n/idioma';

/** Por qué un evento de pago no deja comprar ahora mismo. */
export type MotivoSinVenta = 'cargando' | 'abre' | 'cerrada' | 'recargar' | 'error';

export interface AvisoDeVenta {
  readonly motivo: MotivoSinVenta;
  /** Fecha y hora de apertura en la zona del evento (solo con `abre`). */
  readonly fecha: string | null;
}

type EventoConVenta = Pick<
  PublicEventDetail,
  'registration_mode' | 'ticket_sales' | 'ticket_sales_opens_at' | 'timezone'
>;

/**
 * Aviso que sustituye la compra en un evento de pago sin entradas a la venta
 * ahora mismo, o `null` si se puede comprar (o el evento no es de pago).
 *
 * `tiposVendibles` es lo que el formulario acaba de cargar: `null` en la ficha,
 * que no los carga y se fía de `ticket_sales`. Con la página abierta desde
 * antes de la apertura, `ticket_sales` dice «abre» pero la hora ya pasó: la
 * ficha deja inscribirse y el formulario pide recargar.
 */
export function avisoDeVenta(
  evento: EventoConVenta,
  tiposVendibles: number | null,
  errorAlCargarTipos = false,
  ahora = Date.now(),
  idioma: string = IDIOMA_POR_DEFECTO,
): AvisoDeVenta | null {
  if (evento.registration_mode !== 'paid' || (tiposVendibles ?? 0) > 0) {
    return null;
  }
  if (errorAlCargarTipos) {
    return { motivo: 'error', fecha: null };
  }
  const abre = evento.ticket_sales_opens_at;
  if (evento.ticket_sales === 'upcoming' && abre && Date.parse(abre) > ahora) {
    return {
      motivo: 'abre',
      fecha: formatearFecha(abre, idioma, {
        dateStyle: 'long',
        timeStyle: 'short',
        timeZone: evento.timezone,
      }),
    };
  }
  if (evento.ticket_sales === 'closed') {
    return { motivo: 'cerrada', fecha: null };
  }
  return tiposVendibles === null ? null : { motivo: 'recargar', fecha: null };
}

/** Texto del aviso, y un botón para recargar cuando la venta pudo abrir con la
 * página ya cargada. Texto, no un botón deshabilitado: no hay acción posible. */
@Component({
  selector: 'app-aviso-venta-entradas',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button],
  template: `
    <ng-container *transloco="let t">
      <app-alert [tone]="aviso().motivo === 'error' ? 'error' : 'info'">
        {{ t('publico.ventaEntradas.' + aviso().motivo, { fecha: aviso().fecha }) }}
        @if (aviso().motivo === 'recargar' || aviso().motivo === 'error') {
          <p>
            <app-button variant="secundario" type="button" (pulsado)="recargar()">
              {{ t('publico.ventaEntradas.botonRecargar') }}
            </app-button>
          </p>
        }
      </app-alert>
    </ng-container>
  `,
})
export class AvisoVentaEntradas {
  readonly aviso = input.required<AvisoDeVenta>();
  private readonly documento = inject(DOCUMENT);

  protected recargar(): void {
    this.documento.defaultView?.location.reload();
  }
}
