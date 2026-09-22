import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService, esPersonalDePlataforma } from '../../../core/auth/auth.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';

/** Formulario de acceso al panel. */
@Component({
  selector: 'app-login-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card, Input, AuthFrame],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('admin.login.titulo')">
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
          <p>
            <a routerLink="/recuperar-contrasena">{{ t('admin.login.olvidasteContrasena') }}</a>
          </p>
          <p>
            {{ t('admin.login.sinCuenta') }}
            <a routerLink="/registro">{{ t('admin.login.registrate') }}</a>
          </p>
        </app-card>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    app-card {
      width: min(24rem, 100%);
      margin: var(--space-lg) auto;
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
      // Un `redirigir` explícito (enlace profundo, invitación, aviso por
      // correo) siempre gana: la lógica de espacio de trabajo de abajo solo
      // decide un destino por defecto cuando nadie pidió uno concreto —
      // si no, un organizador con 2+ espacios perdía su destino real y
      // aterrizaba en el selector (hallazgo de red-team).
      const redirigirExplicito = this.ruta.snapshot.queryParamMap.get('redirigir');
      let destino = redirigirExplicito ?? '/dashboard';
      if (!redirigirExplicito) {
        try {
          const organizaciones = await this.auth.listMyOrganizations();
          const esPlataforma = esPersonalDePlataforma(this.auth.currentUser());
          if (organizaciones.length === 0 && esPlataforma) {
            // Su único espacio real es la plataforma: no tiene sentido mandarlo
            // a un escritorio de organización que no existe.
            destino = '/admin';
          } else if (organizaciones.length + (esPlataforma ? 1 : 0) > 1) {
            // 2+ espacios de trabajo: elegir cuál usar antes de entrar.
            destino = '/espacio-de-trabajo';
          }
          // 1 organización y sin rol de plataforma: se queda en '/dashboard'.
        } catch {
          // Fallo al contar espacios tras un login ya válido (sesión creada,
          // cookie de refresco emitida): no es motivo para abortar el login,
          // mismo criterio que `admin-shell.ts::cargarOrganizaciones`, que ya
          // trata esta misma llamada como no crítica.
        }
      }
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
