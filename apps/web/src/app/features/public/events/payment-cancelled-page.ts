import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

/**
 * Pantalla de `cancel_url` de la Checkout Session de Stripe (fase 6 del PRD,
 * fase 4 de trabajo): la persona ha cancelado el pago desde el propio
 * Checkout hosted de Stripe, sin llegar a pagar. Puramente informativa —
 * `checkout_service.py::crear_sesion_de_pago` nunca ha marcado nada como
 * pagado en este camino, así que no hay ningún estado real que consultar
 * (a diferencia de `payment-return.ts`).
 */
@Component({
  selector: 'app-payment-cancelled-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      <div class="pagina">
        <app-card [heading]="t('pago.cancelado.titulo')">
          <app-alert tone="info">{{ t('pago.cancelado.detalle') }}</app-alert>
          @if (slug) {
            <p>
              <a [routerLink]="['/eventos', slug]">{{ t('pago.cancelado.volverAlEvento') }}</a>
            </p>
          }
        </app-card>
      </div>
    </ng-container>
  `,
  styles: `
    .pagina {
      display: grid;
      place-items: center;
      padding: var(--space-lg) 0;
    }
    app-card {
      width: min(28rem, 100%);
      display: grid;
      gap: var(--space-md);
      text-align: center;
    }
  `,
})
export class PaymentCancelledPage {
  private readonly ruta = inject(ActivatedRoute);

  protected readonly slug: string | null = this.ruta.snapshot.queryParamMap.get('slug');
}
