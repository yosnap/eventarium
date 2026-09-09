import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { PaymentsService, StripeAccountStatus } from '../../../core/payments/payments.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';

type EstadoVisual = 'sin_conectar' | 'desautorizada' | 'pendiente' | 'operativa';

function estadoVisualDe(estado: StripeAccountStatus | null): EstadoVisual {
  if (estado === null || !estado.connected) {
    return 'sin_conectar';
  }
  if (estado.deauthorized_at) {
    return 'desautorizada';
  }
  return estado.charges_enabled ? 'operativa' : 'pendiente';
}

/**
 * Conexión Stripe Connect de la organización (fase 6 del PRD, fase 2 de
 * trabajo): cuatro estados visuales (sin conectar / conectada sin
 * `charges_enabled` / operativa / desconectada con reconexión) y la
 * sincronización manual, además de la automática al volver del onboarding.
 *
 * La plataforma no cobra comisión ni custodia el dinero: el cargo ocurre
 * directamente en la cuenta de la organización (decisiones #2/#3 del plan).
 */
@Component({
  selector: 'app-stripe-connection',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.stripe.titulo') }}</h1>
      <p>{{ t('admin.stripe.aviso') }}</p>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <div aria-live="polite">
          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <app-card>
            @switch (estadoVisual()) {
              @case ('sin_conectar') {
                <app-alert tone="info">{{ t('admin.stripe.estadoSinConectar') }}</app-alert>
                <p class="advertencia-salida">{{ t('admin.stripe.advertenciaSalida') }}</p>
                <app-button [loading]="iniciandoOnboarding()" (pulsado)="conectar()">
                  {{ t('admin.stripe.conectar') }}
                </app-button>
              }
              @case ('pendiente') {
                <app-alert tone="info">{{ t('admin.stripe.estadoPendiente') }}</app-alert>
                <div class="acciones">
                  <app-button [loading]="iniciandoOnboarding()" (pulsado)="conectar()">
                    {{ t('admin.stripe.continuarOnboarding') }}
                  </app-button>
                  <app-button
                    variant="secundario"
                    [loading]="sincronizando()"
                    (pulsado)="sincronizar()"
                  >
                    {{ t('admin.stripe.actualizarEstado') }}
                  </app-button>
                </div>
              }
              @case ('operativa') {
                <app-alert tone="exito">{{ t('admin.stripe.estadoOperativa') }}</app-alert>
                <app-button
                  variant="secundario"
                  [loading]="sincronizando()"
                  (pulsado)="sincronizar()"
                >
                  {{ t('admin.stripe.actualizarEstado') }}
                </app-button>
              }
              @case ('desautorizada') {
                <app-alert tone="error">{{ t('admin.stripe.estadoDesautorizada') }}</app-alert>
                <p class="advertencia-salida">{{ t('admin.stripe.advertenciaSalida') }}</p>
                <app-button [loading]="iniciandoOnboarding()" (pulsado)="conectar()">
                  {{ t('admin.stripe.reconectar') }}
                </app-button>
              }
            }
          </app-card>
        </div>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    .acciones {
      display: flex;
      gap: var(--space-md);
      flex-wrap: wrap;
      margin-top: var(--space-sm);
    }
    .advertencia-salida {
      color: var(--color-text-muted, #6b7280);
      font-size: 0.875rem;
    }
    app-alert + .advertencia-salida {
      margin-top: var(--space-xs);
    }
    app-card app-button {
      margin-top: var(--space-sm);
    }
  `,
})
export class StripeConnection {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly payments = inject(PaymentsService);
  private readonly transloco = inject(TranslocoService);
  private readonly route = inject(ActivatedRoute);

  protected readonly cargando = signal(true);
  protected readonly iniciandoOnboarding = signal(false);
  protected readonly sincronizando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly estado = signal<StripeAccountStatus | null>(null);
  protected readonly estadoVisual = computed(() => estadoVisualDe(this.estado()));

  private organizationId: string | null = null;

  constructor() {
    void this.inicializar();
  }

  private async inicializar(): Promise<void> {
    this.cargando.set(true);
    try {
      const organizacion = await firstValueFrom(
        this.http.get<{ id: string }>(this.api.url('/organizations/me')),
      );
      this.organizationId = organizacion.id;

      // Al volver del onboarding (`return_url`/`refresh_url`) el estado real
      // se consulta a Stripe, nunca se asume por el mero retorno.
      const volviendoDeOnboarding = this.route.snapshot.queryParamMap.has('onboarding');
      this.estado.set(
        volviendoDeOnboarding
          ? await this.payments.sync(this.organizationId)
          : await this.payments.getStatus(this.organizationId),
      );
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.stripe.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected async conectar(): Promise<void> {
    if (!this.organizationId) return;
    this.error.set(null);
    this.iniciandoOnboarding.set(true);
    try {
      const url = await this.payments.startOnboarding(this.organizationId);
      window.location.href = url;
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.stripe.error'),
      );
      this.iniciandoOnboarding.set(false);
    }
  }

  protected async sincronizar(): Promise<void> {
    if (!this.organizationId) return;
    this.error.set(null);
    this.sincronizando.set(true);
    try {
      this.estado.set(await this.payments.sync(this.organizationId));
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.stripe.error'),
      );
    } finally {
      this.sincronizando.set(false);
    }
  }
}
