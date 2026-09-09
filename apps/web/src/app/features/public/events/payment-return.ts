import {
  ChangeDetectionStrategy,
  Component,
  type OnDestroy,
  inject,
  signal,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { PublicCheckoutService } from '../../../core/payments/public-checkout.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';

type Estado = 'comprobando' | 'confirmado' | 'pendiente' | 'fallido' | 'error';

/** Esperas (ms) entre reintentos automáticos: crecientes y **acotadas** —
 * nunca una espera indefinida sin salida. Agotados, la persona sigue teniendo
 * el botón manual de reintentar. */
const ESPERAS_REINTENTO_AUTOMATICO_MS = [2000, 4000, 8000, 8000, 8000] as const;

/**
 * Pantalla de retorno tras el pago (fase 6 del PRD, fase 4 de trabajo):
 * `success_url`/`cancel_url` de la Checkout Session de Stripe apuntan aquí y
 * a `/pago/cancelado` respectivamente, con `registration_id` y `slug` en la
 * query (`checkout_service.py::crear_sesion_de_pago`).
 *
 * **El mero retorno desde Stripe no confirma nada.** El webhook
 * `checkout.session.completed` es la única fuente de verdad (ver
 * `phase-04-checkout-webhooks-y-confirmacion.md`); esta pantalla solo
 * pregunta al backend por el estado ya persistido
 * (`GET /public/events/{slug}/checkout/{registration_id}/status`) y refleja
 * lo que encuentra. Si todavía no ha llegado (carrera normal entre el
 * navegador volviendo y el webhook procesándose), reintenta automáticamente
 * un número acotado de veces con espera creciente y, agotadas, deja un botón
 * manual — nunca un spinner indefinido.
 */
@Component({
  selector: 'app-payment-return',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" class="pagina">
        <app-card [heading]="t('pago.retorno.titulo')">
          <div aria-live="polite">
            @switch (estado()) {
              @case ('comprobando') {
                <app-alert tone="info">{{ t('pago.retorno.comprobando') }}</app-alert>
              }
              @case ('confirmado') {
                <app-alert tone="exito" [title]="t('pago.retorno.confirmadoTitulo')">
                  {{ t('pago.retorno.confirmadoDetalle') }}
                </app-alert>
              }
              @case ('pendiente') {
                <app-alert tone="info" [title]="t('pago.retorno.pendienteTitulo')">
                  {{ t('pago.retorno.pendienteDetalle') }}
                </app-alert>
                <app-button type="button" [loading]="reintentando()" (click)="reintentar()">
                  {{ t('pago.retorno.reintentar') }}
                </app-button>
              }
              @case ('fallido') {
                <app-alert tone="error" [title]="t('pago.retorno.fallidoTitulo')">
                  {{ t('pago.retorno.fallidoDetalle') }}
                </app-alert>
              }
              @case ('error') {
                <app-alert tone="error" [title]="t('pago.retorno.errorTitulo')">
                  {{ t('pago.retorno.errorDetalle') }}
                </app-alert>
                <app-button type="button" [loading]="reintentando()" (click)="reintentar()">
                  {{ t('pago.retorno.reintentar') }}
                </app-button>
              }
            }
          </div>

          @if (slug) {
            <p>
              <a [routerLink]="['/eventos', slug]">{{ t('pago.retorno.volverAlEvento') }}</a>
            </p>
          }
        </app-card>
      </main>
    </ng-container>
  `,
  styles: `
    .pagina {
      display: grid;
      place-items: center;
      min-height: 100vh;
      padding: var(--space-lg);
      background-color: var(--color-surface-muted);
    }
    app-card {
      width: min(28rem, 100%);
      display: grid;
      gap: var(--space-md);
      text-align: center;
    }
  `,
})
export class PaymentReturnPage implements OnDestroy {
  private readonly ruta = inject(ActivatedRoute);
  private readonly checkout = inject(PublicCheckoutService);

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly reintentando = signal(false);
  protected readonly slug: string | null;

  private readonly registrationId: string | null;
  private intentosAutomaticos = 0;
  private temporizador: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    const parametros = this.ruta.snapshot.queryParamMap;
    this.slug = parametros.get('slug');
    this.registrationId = parametros.get('registration_id');
    if (!this.slug || !this.registrationId) {
      this.estado.set('error');
      return;
    }
    void this.comprobar();
  }

  ngOnDestroy(): void {
    this.cancelarTemporizador();
  }

  private cancelarTemporizador(): void {
    if (this.temporizador !== null) {
      clearTimeout(this.temporizador);
      this.temporizador = null;
    }
  }

  private async comprobar(): Promise<void> {
    if (!this.slug || !this.registrationId) {
      this.estado.set('error');
      return;
    }
    try {
      const resultado = await this.checkout.getStatus(this.slug, this.registrationId);
      if (resultado.registration_status === 'confirmed') {
        this.estado.set('confirmado');
        return;
      }
      if (
        resultado.registration_status === 'cancelled' ||
        resultado.payment_status === 'expired'
      ) {
        this.estado.set('fallido');
        return;
      }
      this.estado.set('pendiente');
      this.programarReintentoAutomatico();
    } catch {
      // Un error de red o de servidor no es lo mismo que «pago no
      // confirmado»: no debe presentarse como `fallido` (que implicaría que
      // sí se consultó y el pago no llegó), sino como un error propio,
      // reintentable a mano.
      this.estado.set('error');
    }
  }

  private programarReintentoAutomatico(): void {
    if (this.intentosAutomaticos >= ESPERAS_REINTENTO_AUTOMATICO_MS.length) {
      return;
    }
    const espera = ESPERAS_REINTENTO_AUTOMATICO_MS[this.intentosAutomaticos];
    this.intentosAutomaticos += 1;
    this.temporizador = setTimeout(() => void this.comprobar(), espera);
  }

  protected async reintentar(): Promise<void> {
    this.cancelarTemporizador();
    this.reintentando.set(true);
    this.estado.set('comprobando');
    try {
      await this.comprobar();
    } finally {
      this.reintentando.set(false);
    }
  }
}
