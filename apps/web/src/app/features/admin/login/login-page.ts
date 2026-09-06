import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';

/** Formulario de acceso al panel. */
@Component({
  selector: 'app-login-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" class="pagina">
        <app-card [heading]="t('admin.login.titulo')">
          <form (submit)="enviar($event)" novalidate>
            <app-input
              [label]="t('admin.login.email')"
              type="email"
              autocomplete="username"
              [required]="true"
              [error]="errorEmail()"
              [(value)]="email"
            />
            <app-input
              [label]="t('admin.login.password')"
              type="password"
              autocomplete="current-password"
              [required]="true"
              [error]="errorPassword()"
              [(value)]="password"
            />

            @if (error(); as mensaje) {
              <app-alert tone="error" [title]="t('admin.login.error')">{{ mensaje }}</app-alert>
            }

            <app-button type="submit" [loading]="enviando()">
              {{ enviando() ? t('admin.login.entrando') : t('admin.login.entrar') }}
            </app-button>
          </form>
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
      width: min(24rem, 100%);
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
  `,
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly ruta = inject(ActivatedRoute);
  private readonly transloco = inject(TranslocoService);

  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly enviando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errorEmail = signal<string | null>(null);
  protected readonly errorPassword = signal<string | null>(null);

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);

    // Validación propia en vez de la nativa del navegador: sus mensajes no se pueden
    // traducir ni asociar al campo con aria-describedby.
    this.errorEmail.set(
      this.email().trim() ? null : this.transloco.translate('admin.login.emailRequerido'),
    );
    this.errorPassword.set(
      this.password() ? null : this.transloco.translate('admin.login.passwordRequerido'),
    );
    if (this.errorEmail() || this.errorPassword()) {
      return;
    }

    this.enviando.set(true);
    try {
      await this.auth.login(this.email().trim(), this.password());
      const destino = this.ruta.snapshot.queryParamMap.get('redirigir') ?? '/admin';
      await this.router.navigateByUrl(destino);
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.login.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
