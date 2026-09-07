import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

/**
 * Alta de una cuenta. CSR, como `admin/login`: es un flujo transaccional, no
 * contenido público indexable.
 *
 * La respuesta es siempre la misma exista o no ya la cuenta (anti-enumeración), así
 * que tras enviar el formulario se muestra el mismo mensaje de éxito en ambos casos.
 */
@Component({
  selector: 'app-register-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card, Input, TurnstileWidget],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" class="pagina">
        <app-card [heading]="t('registro.titulo')">
          @if (enviado()) {
            <app-alert tone="exito" [title]="t('registro.exitoTitulo')">
              {{ t('registro.exitoDetalle') }}
            </app-alert>
          } @else {
            <form (submit)="enviar($event)" novalidate>
              <app-input
                [label]="t('registro.nombre')"
                autocomplete="name"
                [required]="true"
                [error]="errorNombre()"
                [(value)]="fullName"
              />
              <app-input
                [label]="t('registro.email')"
                type="email"
                autocomplete="email"
                [required]="true"
                [error]="errorEmail()"
                [(value)]="email"
              />
              <app-input
                [label]="t('registro.password')"
                type="password"
                autocomplete="new-password"
                [required]="true"
                [error]="errorPassword()"
                [(value)]="password"
              />
              <p class="ayuda">{{ t('registro.passwordAyuda') }}</p>

              <app-turnstile-widget (resuelto)="turnstileToken.set($event)" />

              @if (error(); as mensaje) {
                <app-alert tone="error" [title]="t('registro.error')">{{ mensaje }}</app-alert>
              }

              <app-button type="submit" [loading]="enviando()">
                {{ enviando() ? t('registro.creando') : t('registro.crearCuenta') }}
              </app-button>
            </form>
          }

          <p>
            <a routerLink="/admin/login">{{ t('registro.yaTengoCuenta') }}</a>
          </p>
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
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
    .ayuda {
      margin: calc(var(--space-md) * -1) 0 0;
      font-size: 0.875rem;
      color: var(--color-text-muted, inherit);
    }
  `,
})
export class RegisterPage {
  private readonly auth = inject(AuthService);
  private readonly transloco = inject(TranslocoService);

  protected readonly fullName = signal('');
  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly turnstileToken = signal<string | null>(null);
  protected readonly enviando = signal(false);
  protected readonly enviado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errorNombre = signal<string | null>(null);
  protected readonly errorEmail = signal<string | null>(null);
  protected readonly errorPassword = signal<string | null>(null);

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);

    this.errorNombre.set(
      this.fullName().trim() ? null : this.transloco.translate('registro.nombreRequerido'),
    );
    this.errorEmail.set(
      this.email().trim() ? null : this.transloco.translate('registro.emailRequerido'),
    );
    this.errorPassword.set(
      this.password().length >= 8 ? null : this.transloco.translate('registro.passwordRequerida'),
    );
    if (this.errorNombre() || this.errorEmail() || this.errorPassword()) {
      return;
    }

    this.enviando.set(true);
    try {
      await this.auth.register(
        this.email().trim(),
        this.password(),
        this.fullName().trim(),
        this.turnstileToken() ?? '',
      );
      this.enviado.set(true);
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('registro.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
