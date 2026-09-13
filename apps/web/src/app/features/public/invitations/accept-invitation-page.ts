import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { PasswordStrength, isPasswordValid } from '../../../shared/ui/password-strength';
import { Reveal } from '../../../shared/ui/reveal.directive';

type Estado = 'comprobando' | 'formulario' | 'yaTieneCuenta' | 'sinToken' | 'error' | 'exito';

interface InvitationPublicResponse {
  readonly organization_name: string;
  readonly role_name: string;
  readonly account_has_password: boolean;
}

/**
 * Consume el token de invitación de la URL. CSR, mismo patrón que
 * `verify-email-page.ts`/`reset-password-page.ts`.
 *
 * Tres estados de token distintos (caducado, revocado, ya aceptado) llegan como el
 * mismo `estado: 'error'` aquí: el mensaje que los distingue lo pone la API
 * (`detail` del `problem+json`), no esta pantalla — es el mismo criterio que ya usan
 * `member-form`/`invitations-panel` («el mensaje del backend ya es traducible»).
 */
@Component({
  selector: 'app-accept-invitation-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    AuthFrame,
    Alert,
    Button,
    Card,
    Input,
    PasswordStrength,
    Reveal,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('invitacion.titulo')">
        <div class="envoltura" appReveal>
          <app-card [heading]="t('invitacion.titulo')">
            <div aria-live="assertive">
              @switch (estado()) {
                @case ('comprobando') {
                  <app-alert tone="info">{{ t('invitacion.comprobando') }}</app-alert>
                }
                @case ('sinToken') {
                  <app-alert tone="error" [title]="t('invitacion.errorTitulo')">
                    {{ t('invitacion.sinToken') }}
                  </app-alert>
                }
                @case ('error') {
                  <app-alert tone="error" [title]="t('invitacion.errorTitulo')">
                    {{ mensajeError() }}
                  </app-alert>
                }
                @case ('yaTieneCuenta') {
                  <app-alert tone="info" [title]="t('invitacion.yaTieneCuentaTitulo')">
                    {{ t('invitacion.yaTieneCuentaDetalle') }}
                    <p>
                      <a routerLink="/acceder">{{ t('registro.yaTengoCuenta') }}</a>
                    </p>
                  </app-alert>
                }
                @case ('exito') {
                  <app-alert tone="exito" [title]="t('invitacion.exitoTitulo')">
                    {{ t('invitacion.exitoDetalle', { organizacion: organizationName() }) }}
                    <p>
                      <a routerLink="/acceder">{{ t('invitacion.irAAcceder') }}</a>
                    </p>
                  </app-alert>
                }
                @case ('formulario') {
                  <p class="descripcion">
                    {{
                      t('invitacion.descripcion', {
                        organizacion: organizationName(),
                        rol: roleName(),
                      })
                    }}
                  </p>
                  <form (submit)="aceptar($event)" novalidate>
                    <app-input
                      fieldId="invitacion-nombre"
                      [label]="t('invitacion.nombre')"
                      autocomplete="given-name"
                      [required]="true"
                      [error]="errorNombre()"
                      [(value)]="firstName"
                    />
                    <app-input
                      fieldId="invitacion-apellidos"
                      [label]="t('invitacion.apellidos')"
                      autocomplete="family-name"
                      [required]="true"
                      [error]="errorApellidos()"
                      [(value)]="lastName"
                    />
                    <app-input
                      fieldId="invitacion-password"
                      [label]="t('invitacion.password')"
                      type="password"
                      autocomplete="new-password"
                      [required]="true"
                      [(value)]="password"
                    />
                    <app-password-strength [password]="password()" />
                    @if (errorEnvio(); as mensaje) {
                      <app-alert tone="error">{{ mensaje }}</app-alert>
                    }
                    <app-button type="submit" [loading]="enviando()">
                      {{ enviando() ? t('invitacion.uniendote') : t('invitacion.unirme') }}
                    </app-button>
                  </form>
                }
              }
            </div>
          </app-card>
        </div>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    .envoltura {
      width: min(28rem, 100%);
    }
    .descripcion {
      margin-top: 0;
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
  `,
})
export class AcceptInvitationPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly transloco = inject(TranslocoService);
  private readonly token = this.ruta.snapshot.queryParamMap.get('token');

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly mensajeError = signal('');
  protected readonly organizationName = signal('');
  protected readonly roleName = signal('');

  protected readonly firstName = signal('');
  protected readonly lastName = signal('');
  protected readonly password = signal('');
  protected readonly errorNombre = signal<string | null>(null);
  protected readonly errorApellidos = signal<string | null>(null);
  protected readonly errorEnvio = signal<string | null>(null);
  protected readonly enviando = signal(false);

  constructor() {
    if (!this.token) {
      this.estado.set('sinToken');
      return;
    }
    void this.consultar(this.token);
  }

  private async consultar(token: string): Promise<void> {
    try {
      const datos = await firstValueFrom(
        this.http.get<InvitationPublicResponse>(this.api.url(`/public/invitations/${token}`)),
      );
      this.organizationName.set(datos.organization_name);
      this.roleName.set(datos.role_name);
      this.estado.set(datos.account_has_password ? 'yaTieneCuenta' : 'formulario');
    } catch (error) {
      this.estado.set('error');
      this.mensajeError.set(
        error instanceof ApiError ? error.message : this.transloco.translate('invitacion.error'),
      );
    }
  }

  protected async aceptar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.errorEnvio.set(null);

    this.errorNombre.set(
      this.firstName().trim() ? null : this.transloco.translate('invitacion.nombreRequerido'),
    );
    this.errorApellidos.set(
      this.lastName().trim() ? null : this.transloco.translate('invitacion.apellidosRequeridos'),
    );
    if (!isPasswordValid(this.password())) {
      this.errorEnvio.set(this.transloco.translate('registro.passwordSinComplejidad'));
    }
    if (this.errorNombre() || this.errorApellidos() || this.errorEnvio()) {
      return;
    }

    this.enviando.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/public/invitations/${this.token}/accept`), {
          first_name: this.firstName().trim(),
          last_name: this.lastName().trim(),
          password: this.password(),
        }),
      );
      this.estado.set('exito');
    } catch (error) {
      this.errorEnvio.set(
        error instanceof ApiError ? error.message : this.transloco.translate('invitacion.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
