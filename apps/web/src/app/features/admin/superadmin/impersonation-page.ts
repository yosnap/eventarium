import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { Select, SelectOption } from '../../../shared/ui/select';

interface Organizacion {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
}

interface Miembro {
  readonly user_id: string;
  readonly nombre: string;
  readonly email_enmascarado: string;
  readonly role_key: string;
  readonly suplantable: boolean;
}

/**
 * Entrada a una sesión de impersonación: elegir organización, elegir persona,
 * motivo y contraseña. La sesión resultante es de **solo lectura**.
 *
 * Exige la contraseña del propio administrador (igual que las operaciones
 * RGPD): suplantar da acceso a todos los datos de una persona, así que no basta
 * con tener la sesión abierta.
 */
@Component({
  selector: 'app-impersonation-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, Select],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.plataforma.impersonar.titulo') }}</h1>
      <p class="descripcion">{{ t('admin.plataforma.impersonar.descripcion') }}</p>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }

      <app-card [heading]="t('admin.plataforma.impersonar.destino')">
        <app-select
          [label]="t('admin.plataforma.impersonar.organizacion')"
          [options]="opcionesDeOrganizacion()"
          [(value)]="organizacionElegida"
          (valueChange)="cargarMiembros($event)"
          [placeholder]="t('admin.plataforma.impersonar.eligeOrganizacion')"
        />

        @if (organizacionElegida()) {
          <app-select
            [label]="t('admin.plataforma.impersonar.persona')"
            [options]="opcionesDeMiembro()"
            [(value)]="miembroElegido"
            [placeholder]="t('admin.plataforma.impersonar.eligePersona')"
            [hint]="t('admin.plataforma.impersonar.soloSuplantables')"
          />
        }

        @if (miembroElegido()) {
          <form (submit)="entrar($event)">
            <app-input
              [label]="t('admin.plataforma.impersonar.motivo')"
              [required]="true"
              [(value)]="motivo"
            />
            <app-input
              [label]="t('admin.plataforma.impersonar.contrasena')"
              type="password"
              autocomplete="current-password"
              [required]="true"
              [(value)]="contrasena"
              [hint]="t('admin.plataforma.impersonar.contrasenaAyuda')"
            />
            <app-button type="submit" [loading]="entrando()">
              {{ t('admin.plataforma.impersonar.entrar') }}
            </app-button>
          </form>
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    h1 {
      margin-block-end: 0.25rem;
    }
    .descripcion {
      color: var(--muted);
      margin-block-end: 1.5rem;
      max-width: 68ch;
    }
    form {
      display: grid;
      gap: 1rem;
      max-width: 32rem;
      margin-block-start: 1rem;
    }
  `,
})
export class ImpersonationPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly transloco = inject(TranslocoService);

  readonly organizaciones = signal<readonly Organizacion[]>([]);
  readonly miembros = signal<readonly Miembro[]>([]);
  readonly organizacionElegida = signal('');
  readonly miembroElegido = signal('');
  readonly motivo = signal('');
  readonly contrasena = signal('');
  readonly entrando = signal(false);
  readonly error = signal<string | null>(null);

  readonly opcionesDeOrganizacion = signal<readonly SelectOption[]>([]);
  readonly opcionesDeMiembro = signal<readonly SelectOption[]>([]);

  constructor() {
    void this.cargarOrganizaciones();
  }

  private async cargarOrganizaciones(): Promise<void> {
    try {
      const lista = await firstValueFrom(
        this.http.get<readonly Organizacion[]>(this.api.url('/admin/organizations'), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.organizaciones.set(lista);
      this.opcionesDeOrganizacion.set(lista.map((o) => ({ value: o.id, label: o.name })));
    } catch {
      this.error.set(this.transloco.translate('admin.plataforma.impersonar.errorCarga'));
    }
  }

  async cargarMiembros(organizacionId: string): Promise<void> {
    this.miembroElegido.set('');
    this.miembros.set([]);
    this.opcionesDeMiembro.set([]);
    if (!organizacionId) {
      return;
    }
    try {
      const lista = await firstValueFrom(
        this.http.get<readonly Miembro[]>(
          this.api.url(`/admin/organizations/${organizacionId}/members`),
          { headers: this.api.serverForwardHeaders() },
        ),
      );
      this.miembros.set(lista);
      // Solo se ofrecen los suplantables: un administrador de plataforma no
      // puede suplantarse entre sí, y el backend lo rechazaría igual.
      this.opcionesDeMiembro.set(
        lista
          .filter((m) => m.suplantable)
          .map((m) => ({ value: m.user_id, label: `${m.nombre} (${m.email_enmascarado})` })),
      );
    } catch {
      this.error.set(this.transloco.translate('admin.plataforma.impersonar.errorCarga'));
    }
  }

  async entrar(evento: Event): Promise<void> {
    evento.preventDefault();
    const miembro = this.miembros().find((m) => m.user_id === this.miembroElegido());
    if (!miembro) {
      return;
    }

    this.entrando.set(true);
    this.error.set(null);
    try {
      await this.auth.impersonar({
        userId: miembro.user_id,
        organizationId: this.organizacionElegida(),
        reason: this.motivo().trim(),
        password: this.contrasena(),
        nombreVisible: miembro.nombre,
      });
      // Recarga completa: la aplicación entera debe repintarse con la sesión
      // suplantada (su organización, sus permisos), no quedarse con el estado
      // del administrador.
      window.location.reload();
    } catch (fallo) {
      this.error.set(
        fallo instanceof ApiError
          ? fallo.message
          : this.transloco.translate('admin.plataforma.impersonar.errorEntrar'),
      );
    } finally {
      this.entrando.set(false);
    }
  }
}
