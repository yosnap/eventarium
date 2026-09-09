import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  type OnInit,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';

type PaymentStatus = 'pending' | 'paid' | 'refunded' | 'partially_refunded' | 'expired';
type RefundStatus = 'pending' | 'submitted' | 'succeeded' | 'failed';
type NoAutoRefundReason = 'evento_ya_empezado' | 'entrada_usada' | 'fuera_de_plazo';

interface PaymentRefund {
  readonly id: string;
  readonly amount_cents: number;
  readonly reason: 'cancellation' | 'manual';
  readonly revoke_ticket: boolean;
  readonly status: RefundStatus;
  readonly error: string | null;
  readonly attempts: number;
}

interface Payment {
  readonly id: string;
  readonly registration_id: string | null;
  readonly email: string | null;
  readonly ticket_type_name: string | null;
  readonly status: PaymentStatus;
  readonly amount_cents: number;
  readonly discount_cents: number;
  readonly currency: string;
  readonly refunded_cents: number;
  readonly paid_at: string | null;
  readonly no_auto_refund_reason: NoAutoRefundReason | null;
  readonly refunds: PaymentRefund[];
}

function euros(cents: number): string {
  return (cents / 100).toFixed(2);
}

function pendiente(pago: Payment): number {
  return pago.amount_cents - pago.refunded_cents;
}

function tieneReembolsoEnCurso(pago: Payment): boolean {
  return pago.refunds.some((r) => r.status === 'pending' || r.status === 'submitted');
}

function tieneReembolsoAgotado(pago: Payment): boolean {
  return pago.refunds.some((r) => r.status === 'failed' && r.attempts >= 5);
}

/**
 * Panel de pagos de un evento (fase 6 del PRD, fase 5 de trabajo): estado de
 * cada pago, reembolsos en curso y acción de reembolso manual, total o
 * parcial. El reembolso nunca se ejecuta en esta petición: queda `pending`
 * en el outbox hasta que la tarea programada lo procese contra Stripe, así
 * que el diálogo siempre habla de «reembolso en curso», nunca de
 * «reembolsado».
 */
@Component({
  selector: 'app-event-payments',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.payments.titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (avisoAccion(); as mensaje) {
          <p role="status" aria-live="polite">{{ mensaje }}</p>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (pagos().length === 0) {
          <p>{{ t('admin.events.payments.sinPagos') }}</p>
        } @else {
          <table>
            <caption class="sr-only">
              {{ t('admin.events.payments.titulo') }}
            </caption>
            <thead>
              <tr>
                <th scope="col">{{ t('admin.events.payments.columnaPersona') }}</th>
                <th scope="col">{{ t('admin.events.payments.columnaTipo') }}</th>
                <th scope="col">{{ t('admin.events.payments.columnaEstado') }}</th>
                <th scope="col">{{ t('admin.events.payments.columnaImporte') }}</th>
                <th scope="col">{{ t('admin.events.payments.columnaReembolsado') }}</th>
                <th scope="col">{{ t('admin.events.payments.columnaAcciones') }}</th>
              </tr>
            </thead>
            <tbody>
              @for (pago of pagos(); track pago.id) {
                <tr>
                  <td>{{ pago.email ?? t('admin.events.payments.personaBorrada') }}</td>
                  <td>{{ pago.ticket_type_name ?? '—' }}</td>
                  <td>
                    {{ t('admin.events.payments.estado.' + pago.status) }}
                    @if (tieneReembolsoEnCurso(pago)) {
                      <span class="detalle">{{ t('admin.events.payments.reembolsoEnCurso') }}</span>
                    }
                    @if (tieneReembolsoAgotado(pago)) {
                      <span class="detalle destacado">{{
                        t('admin.events.payments.reembolsoAgotado')
                      }}</span>
                    }
                    @if (pago.no_auto_refund_reason) {
                      <span class="detalle">
                        {{ t('admin.events.payments.sinReembolsoAutomatico.' + pago.no_auto_refund_reason) }}
                      </span>
                    }
                  </td>
                  <td>{{ euros(pago.amount_cents) }} {{ pago.currency.toUpperCase() }}</td>
                  <td>{{ euros(pago.refunded_cents) }} {{ pago.currency.toUpperCase() }}</td>
                  <td>
                    @if (pendiente(pago) > 0) {
                      <app-button
                        variant="secundario"
                        type="button"
                        (pulsado)="abrirDialogo(pago)"
                      >
                        {{ t('admin.events.payments.reembolsar') }}
                      </app-button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </app-card>

      <dialog #dialogo (cancel)="cerrarDialogo()" (close)="cerrarDialogo()">
        @if (pagoSeleccionado(); as pago) {
          <form (submit)="confirmarReembolso($event)" novalidate class="dialogo-contenido">
            <h2>{{ t('admin.events.payments.dialogo.titulo') }}</h2>
            <dl class="resumen">
              <dt>{{ t('admin.events.payments.dialogo.total') }}</dt>
              <dd>{{ euros(pago.amount_cents) }} {{ pago.currency.toUpperCase() }}</dd>
              <dt>{{ t('admin.events.payments.dialogo.yaReembolsado') }}</dt>
              <dd>{{ euros(pago.refunded_cents) }} {{ pago.currency.toUpperCase() }}</dd>
              <dt>{{ t('admin.events.payments.dialogo.pendiente') }}</dt>
              <dd>{{ euros(pendiente(pago)) }} {{ pago.currency.toUpperCase() }}</dd>
            </dl>

            <div class="campo-numero">
              <label for="reembolso-importe">
                {{ t('admin.events.payments.dialogo.importeAReembolsar') }}
              </label>
              <input
                id="reembolso-importe"
                type="number"
                inputmode="decimal"
                min="0.01"
                [max]="euros(pendiente(pago))"
                step="0.01"
                [value]="importeEuros()"
                (input)="importeEuros.set(alTexto($event))"
              />
            </div>

            @if (esParcial(pago)) {
              <label class="campo-casilla">
                <input
                  type="checkbox"
                  [checked]="revocarEntrada()"
                  (change)="revocarEntrada.set(alCasilla($event))"
                />
                {{ t('admin.events.payments.dialogo.revocarEntrada') }}
              </label>
            } @else {
              <p class="ayuda">{{ t('admin.events.payments.dialogo.totalSiempreRevoca') }}</p>
            }

            @if (errorDialogo(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }

            <div class="acciones-dialogo">
              <app-button variant="secundario" type="button" (pulsado)="cerrarDialogo()">
                {{ t('comun.cancelar') }}
              </app-button>
              <app-button type="submit" variant="peligro" [loading]="confirmando()">
                {{ t('admin.events.payments.dialogo.confirmar') }}
              </app-button>
            </div>
          </form>
        }
      </dialog>
    </ng-container>
  `,
  styles: `
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th,
    td {
      text-align: left;
      padding: var(--space-sm);
      border-bottom: 1px solid var(--color-border);
      vertical-align: top;
    }
    .detalle {
      display: block;
      font-size: 0.8125rem;
      color: var(--color-text-muted, #6b7280);
    }
    .destacado {
      color: var(--color-danger);
      font-weight: 600;
    }
    dialog {
      border: none;
      border-radius: var(--radius-md);
      padding: 0;
      max-width: 28rem;
      width: 90vw;
    }
    dialog::backdrop {
      background-color: rgb(0 0 0 / 0.4);
    }
    .dialogo-contenido {
      display: grid;
      gap: var(--space-md);
      padding: var(--space-lg);
    }
    .resumen {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: var(--space-xs) var(--space-md);
      margin: 0;
    }
    .resumen dt {
      color: var(--color-text-muted, #6b7280);
    }
    .resumen dd {
      margin: 0;
      font-weight: 600;
      text-align: right;
    }
    .campo-numero {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-numero input {
      width: 100%;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 2.75rem;
    }
    .campo-casilla {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .ayuda {
      margin: 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.8125rem;
    }
    .acciones-dialogo {
      display: flex;
      justify-content: flex-end;
      gap: var(--space-md);
    }
  `,
})
export class EventPayments implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly dialogoRef = viewChild<ElementRef<HTMLDialogElement>>('dialogo');

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly avisoAccion = signal<string | null>(null);
  protected readonly pagos = signal<Payment[]>([]);

  protected readonly pagoSeleccionado = signal<Payment | null>(null);
  protected readonly importeEuros = signal('');
  protected readonly revocarEntrada = signal(false);
  protected readonly confirmando = signal(false);
  protected readonly errorDialogo = signal<string | null>(null);

  protected readonly euros = euros;
  protected readonly pendiente = pendiente;
  protected readonly tieneReembolsoEnCurso = tieneReembolsoEnCurso;
  protected readonly tieneReembolsoAgotado = tieneReembolsoAgotado;

  ngOnInit(): void {
    void this.cargar();
  }

  protected esParcial(pago: Payment): boolean {
    const importe = Math.round(Number(this.importeEuros().replace(',', '.')) * 100);
    return Number.isFinite(importe) && importe > 0 && importe < pendiente(pago);
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  protected alCasilla(evento: Event): boolean {
    return (evento.target as HTMLInputElement).checked;
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const pagos = await firstValueFrom(
        this.http.get<Payment[]>(this.api.url(`/events/${this.eventId()}/payments`)),
      );
      this.pagos.set([...pagos]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.payments.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected abrirDialogo(pago: Payment): void {
    this.pagoSeleccionado.set(pago);
    this.importeEuros.set(euros(pendiente(pago)));
    this.revocarEntrada.set(false);
    this.errorDialogo.set(null);
    this.dialogoRef()?.nativeElement.showModal();
  }

  protected cerrarDialogo(): void {
    this.dialogoRef()?.nativeElement.close();
    this.pagoSeleccionado.set(null);
  }

  protected async confirmarReembolso(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    const pago = this.pagoSeleccionado();
    if (!pago) {
      return;
    }
    this.errorDialogo.set(null);

    const importeCents = Math.round(Number(this.importeEuros().replace(',', '.')) * 100);
    if (!Number.isFinite(importeCents) || importeCents <= 0) {
      this.errorDialogo.set(this.transloco.translate('admin.events.payments.dialogo.importeInvalido'));
      return;
    }
    if (importeCents > pendiente(pago)) {
      this.errorDialogo.set(
        this.transloco.translate('admin.events.payments.dialogo.importeSuperaPendiente'),
      );
      return;
    }

    const esTotal = importeCents === pendiente(pago);
    this.confirmando.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/events/${this.eventId()}/payments/${pago.id}/refund`), {
          amount_cents: esTotal ? undefined : importeCents,
          revoke_ticket: esTotal ? true : this.revocarEntrada(),
        }),
      );
      this.cerrarDialogo();
      this.avisoAccion.set(this.transloco.translate('admin.events.payments.reembolsoSolicitado'));
      await this.cargar();
    } catch (error) {
      this.errorDialogo.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.payments.error'),
      );
    } finally {
      this.confirmando.set(false);
    }
  }
}
