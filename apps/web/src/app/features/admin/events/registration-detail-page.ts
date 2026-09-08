import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { claveDeEstado, type RegistrationDetail } from './registration-types';

/**
 * Página de detalle de una inscripción: datos de la persona, respuestas a las
 * preguntas personalizadas, consentimientos registrados y las mismas acciones
 * de aprobar/rechazar/cancelar que el listado.
 */
@Component({
  selector: 'app-registration-detail-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, DatePipe, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      <div class="cabecera">
        <h1>{{ t('admin.events.registrations.detalle.titulo') }}</h1>
        <a [routerLink]="['/admin/events', eventId()]">
          <app-button variant="secundario" type="button">
            {{ t('admin.events.registrations.detalle.volver') }}
          </app-button>
        </a>
      </div>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      } @else if (inscripcion(); as inscripcion) {
        @if (accionError(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        <app-card [heading]="t('admin.events.registrations.detalle.datos')">
          <dl class="datos">
            <div>
              <dt>{{ t('admin.events.registrations.detalle.email') }}</dt>
              <dd>{{ inscripcion.email }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.detalle.nombre') }}</dt>
              <dd>{{ inscripcion.full_name }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.detalle.estado') }}</dt>
              <dd>
                <code>{{
                  t('admin.events.registrations.estado' + claveDeEstado(inscripcion.status))
                }}</code>
              </dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.detalle.fechaAlta') }}</dt>
              <dd>{{ inscripcion.created_at | date: 'medium' }}</dd>
            </div>
            @if (inscripcion.verified_at) {
              <div>
                <dt>{{ t('admin.events.registrations.detalle.fechaVerificacion') }}</dt>
                <dd>{{ inscripcion.verified_at | date: 'medium' }}</dd>
              </div>
            }
            @if (inscripcion.approved_at) {
              <div>
                <dt>{{ t('admin.events.registrations.detalle.fechaAprobacion') }}</dt>
                <dd>{{ inscripcion.approved_at | date: 'medium' }}</dd>
              </div>
            }
            @if (inscripcion.confirmed_at) {
              <div>
                <dt>{{ t('admin.events.registrations.detalle.fechaConfirmacion') }}</dt>
                <dd>{{ inscripcion.confirmed_at | date: 'medium' }}</dd>
              </div>
            }
            @if (inscripcion.rejected_at) {
              <div>
                <dt>{{ t('admin.events.registrations.detalle.fechaRechazo') }}</dt>
                <dd>{{ inscripcion.rejected_at | date: 'medium' }}</dd>
              </div>
            }
            @if (inscripcion.cancelled_at) {
              <div>
                <dt>{{ t('admin.events.registrations.detalle.fechaCancelacion') }}</dt>
                <dd>{{ inscripcion.cancelled_at | date: 'medium' }}</dd>
              </div>
            }
            @if (inscripcion.waitlist_promoted_at) {
              <div>
                <dt>{{ t('admin.events.registrations.detalle.fechaPromocion') }}</dt>
                <dd>{{ inscripcion.waitlist_promoted_at | date: 'medium' }}</dd>
              </div>
            }
          </dl>

          <div class="acciones">
            @if (inscripcion.status === 'pending_approval') {
              <app-button
                variant="secundario"
                type="button"
                [loading]="accionEnCurso()"
                (pulsado)="aprobar()"
              >
                {{ t('admin.events.registrations.aprobar') }}
              </app-button>
              <app-button
                variant="peligro"
                type="button"
                [loading]="accionEnCurso()"
                (pulsado)="rechazar()"
              >
                {{ t('admin.events.registrations.rechazar') }}
              </app-button>
            }
            @if (inscripcion.status !== 'cancelled' && inscripcion.status !== 'rejected') {
              <app-button
                variant="peligro"
                type="button"
                [loading]="accionEnCurso()"
                (pulsado)="cancelar()"
              >
                {{ t('admin.events.registrations.cancelar') }}
              </app-button>
            }
          </div>
        </app-card>

        <app-card [heading]="t('admin.events.registrations.detalle.respuestas')">
          @if (inscripcion.answers.length === 0) {
            <p>{{ t('admin.events.registrations.detalle.sinRespuestas') }}</p>
          } @else {
            <dl class="datos">
              @for (respuesta of inscripcion.answers; track respuesta.question_id) {
                <div>
                  <dt>{{ respuesta.label }}</dt>
                  <dd>{{ formatearRespuesta(respuesta.value) }}</dd>
                </div>
              }
            </dl>
          }
        </app-card>

        <app-card [heading]="t('admin.events.registrations.detalle.consentimientos')">
          @if (inscripcion.consent; as consentimiento) {
            <dl class="datos">
              <div>
                <dt>{{ t('admin.events.registrations.detalle.consentimientoDatos') }}</dt>
                <dd>{{ consentimiento.data_processing_accepted_at | date: 'medium' }}</dd>
              </div>
              <div>
                <dt>
                  {{
                    consentimiento.marketing_accepted_at
                      ? t('admin.events.registrations.detalle.consentimientoMarketing')
                      : t('admin.events.registrations.detalle.consentimientoMarketingNo')
                  }}
                </dt>
                @if (consentimiento.marketing_accepted_at) {
                  <dd>{{ consentimiento.marketing_accepted_at | date: 'medium' }}</dd>
                }
              </div>
              <div>
                <dt>
                  {{
                    consentimiento.recording_accepted_at
                      ? t('admin.events.registrations.detalle.consentimientoGrabacion')
                      : t('admin.events.registrations.detalle.consentimientoGrabacionNo')
                  }}
                </dt>
                @if (consentimiento.recording_accepted_at) {
                  <dd>{{ consentimiento.recording_accepted_at | date: 'medium' }}</dd>
                }
              </div>
            </dl>
          } @else {
            <p>{{ t('admin.events.registrations.detalle.sinConsentimientos') }}</p>
          }
        </app-card>
      }
    </ng-container>
  `,
  styles: `
    .cabecera {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: var(--space-md);
      flex-wrap: wrap;
      margin-bottom: var(--space-lg);
    }
    h1 {
      margin: 0;
    }
    app-card {
      display: block;
      margin-bottom: var(--space-lg);
    }
    .datos {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
      gap: var(--space-md);
      margin: 0;
    }
    .datos dt {
      font-size: 0.8125rem;
      color: var(--color-text-muted, #6b7280);
    }
    .datos dd {
      margin: 0;
      font-weight: 500;
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
      flex-wrap: wrap;
      margin-top: var(--space-md);
    }
  `,
})
export class RegistrationDetailPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly route = inject(ActivatedRoute);

  protected readonly claveDeEstado = claveDeEstado;

  protected readonly eventId = signal('');
  protected readonly registrationId = signal('');

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly inscripcion = signal<RegistrationDetail | null>(null);

  protected readonly accionEnCurso = signal(false);
  protected readonly accionError = signal<string | null>(null);

  constructor() {
    const eventId = this.route.snapshot.paramMap.get('id') ?? '';
    const registrationId = this.route.snapshot.paramMap.get('registrationId') ?? '';
    this.eventId.set(eventId);
    this.registrationId.set(registrationId);
    void this.cargar();
  }

  protected formatearRespuesta(valor: string | readonly string[] | null): string {
    if (valor === null) {
      return '—';
    }
    return typeof valor === 'string' ? valor : valor.join(', ');
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const inscripcion = await firstValueFrom(
        this.http.get<RegistrationDetail>(
          this.api.url(`/events/${this.eventId()}/registrations/${this.registrationId()}`),
        ),
      );
      this.inscripcion.set(inscripcion);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrations.detalle.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  private async ejecutarAccion(accion: 'approve' | 'reject' | 'cancel'): Promise<void> {
    this.accionError.set(null);
    this.accionEnCurso.set(true);
    try {
      await firstValueFrom(
        this.http.post(
          this.api.url(
            `/events/${this.eventId()}/registrations/${this.registrationId()}/${accion}`,
          ),
          {},
        ),
      );
      await this.cargar();
    } catch (error) {
      this.accionError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrations.error'),
      );
    } finally {
      this.accionEnCurso.set(false);
    }
  }

  protected aprobar(): void {
    void this.ejecutarAccion('approve');
  }

  protected rechazar(): void {
    void this.ejecutarAccion('reject');
  }

  protected cancelar(): void {
    void this.ejecutarAccion('cancel');
  }
}
