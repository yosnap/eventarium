import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Input } from '../../../shared/ui/input';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Formulario de un campo (email) que pide el magic-link de «Mis eventos».
 *
 * La respuesta es siempre la misma exista o no ese email entre las
 * inscripciones (anti-enumeración, igual que `ForgotPasswordPage`): el
 * mensaje de éxito nunca distingue ambos casos, ni siquiera en el frontend —
 * la decisión de no enumerar es también de UI, no solo de API.
 */
@Component({
  selector: 'app-mis-eventos-solicitar-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Input, Reveal, TurnstileWidget],
  template: `
    <ng-container *transloco="let t">
      <div class="ancho-maximo envoltura" appReveal>
        <h1>{{ t('publico.misEventos.titulo') }}</h1>

        @if (enviado()) {
          <app-alert tone="exito" [title]="t('publico.misEventos.exitoTitulo')">
            {{ t('publico.misEventos.exitoDetalle') }}
          </app-alert>
        } @else {
          <form (submit)="enviar($event)" novalidate>
            <p>{{ t('publico.misEventos.instrucciones') }}</p>
            <app-input
              [label]="t('publico.misEventos.email')"
              type="email"
              autocomplete="email"
              [required]="true"
              [error]="errorEmail()"
              [(value)]="email"
            />
            <app-turnstile-widget (resuelto)="turnstileToken.set($event)" />
            @if (error(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }
            <app-button type="submit" [loading]="enviando()">
              {{ enviando() ? t('publico.misEventos.enviando') : t('publico.misEventos.enviar') }}
            </app-button>
          </form>
        }
      </div>
    </ng-container>
  `,
  styles: `
    .envoltura {
      padding: var(--space-lg) 0;
      max-width: 26rem;
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
  `,
})
export class MisEventosSolicitarPage {
  private readonly registrations = inject(RegistrationsService);
  private readonly transloco = inject(TranslocoService);

  protected readonly email = signal('');
  protected readonly errorEmail = signal<string | null>(null);
  protected readonly turnstileToken = signal<string | null>(null);
  protected readonly enviando = signal(false);
  protected readonly enviado = signal(false);
  protected readonly error = signal<string | null>(null);

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    const correo = this.email().trim();
    this.errorEmail.set(
      EMAIL_RE.test(correo) ? null : this.transloco.translate('registro.emailInvalido'),
    );
    if (this.errorEmail()) {
      return;
    }

    this.enviando.set(true);
    try {
      await this.registrations.requestMisEventosAccess(correo, this.turnstileToken() ?? '');
      this.enviado.set(true);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('publico.misEventos.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
