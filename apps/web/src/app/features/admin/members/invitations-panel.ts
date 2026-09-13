import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { DataTable, DataTableColumn } from '../../../shared/ui/data-table';
import { Input } from '../../../shared/ui/input';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface RoleOption {
  readonly id: string;
  readonly key: string;
  readonly name: string;
}

type EstadoInvitacion = 'pendiente' | 'aceptada' | 'revocada' | 'caducada';

interface Invitation {
  readonly id: string;
  readonly email: string;
  readonly role_id: string;
  readonly role_key: string;
  readonly estado: EstadoInvitacion;
  readonly expires_at: string;
  readonly created_at: string;
}

interface InvitationCreateResponse {
  readonly status: 'added' | 'invited';
}

const TONO_POR_ESTADO: Record<EstadoInvitacion, ChipTone> = {
  pendiente: 'espera',
  aceptada: 'ok',
  revocada: 'apagado',
  caducada: 'apagado',
};

/**
 * Alta (email + rol), listado con estado y reenvío/revocación, dentro de la
 * sección de equipo (fase 2 del plan de invitaciones).
 *
 * El estado se lee siempre por texto, nunca solo por color del chip (mismo
 * criterio de accesibilidad de `chip.ts`): «pendiente», «aceptada»,
 * «revocada», «caducada» son las cuatro palabras, no solo un tono.
 */
@Component({
  selector: 'app-invitations-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Chip, DataTable, Input],
  template: `
    <ng-container *transloco="let t">
      <section class="panel-invitaciones">
        <h2>{{ t('admin.members.invitaciones.titulo') }}</h2>
        <p>{{ t('admin.members.invitaciones.descripcion') }}</p>

        <form (submit)="invitar($event)" novalidate class="formulario-invitar">
          <app-input
            fieldId="invitacion-email"
            [label]="t('admin.members.invitaciones.email')"
            type="email"
            autocomplete="email"
            [required]="true"
            [error]="errorEmail()"
            [(value)]="email"
          />
          <div class="campo-select">
            <label for="invitacion-rol">{{ t('admin.members.invitaciones.rol') }}</label>
            <select id="invitacion-rol" [value]="roleId()" (change)="alElegirRol($event)">
              <option value="" disabled>
                {{ t('admin.members.invitaciones.rolRequerido') }}
              </option>
              @for (rol of roles(); track rol.id) {
                <option [value]="rol.id">{{ rol.name }}</option>
              }
            </select>
            @if (errorRol()) {
              <p class="error">{{ errorRol() }}</p>
            }
          </div>
          <app-button type="submit" [loading]="invitando()">
            {{
              invitando()
                ? t('admin.members.invitaciones.invitando')
                : t('admin.members.invitaciones.invitar')
            }}
          </app-button>
        </form>

        @if (mensaje(); as texto) {
          <app-alert [tone]="mensajeEsError() ? 'error' : 'exito'">{{ texto }}</app-alert>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (invitaciones().length === 0) {
          <p>{{ t('admin.members.invitaciones.sinInvitaciones') }}</p>
        } @else {
          <app-data-table
            [columnas]="columnas()"
            [caption]="t('admin.members.invitaciones.titulo')"
          >
            @for (invitacion of invitaciones(); track invitacion.id) {
              <tr>
                <td>{{ invitacion.email }}</td>
                <td>
                  <code>{{ invitacion.role_key }}</code>
                </td>
                <td>
                  <app-chip [tone]="tonoDe(invitacion.estado)">{{
                    etiquetaDeEstado(invitacion.estado)
                  }}</app-chip>
                </td>
                <td class="acciones">
                  @if (invitacion.estado === 'pendiente' || invitacion.estado === 'caducada') {
                    <app-button
                      variant="secundario"
                      type="button"
                      [loading]="enAccion() === invitacion.id + ':reenviar'"
                      [disabled]="enAccion() !== null && enAccion() !== invitacion.id + ':reenviar'"
                      (pulsado)="reenviar(invitacion.id)"
                    >
                      {{ t('admin.members.invitaciones.reenviar') }}
                    </app-button>
                    <app-button
                      variant="secundario"
                      type="button"
                      [loading]="enAccion() === invitacion.id + ':revocar'"
                      [disabled]="enAccion() !== null && enAccion() !== invitacion.id + ':revocar'"
                      (pulsado)="revocar(invitacion.id)"
                    >
                      {{ t('admin.members.invitaciones.revocar') }}
                    </app-button>
                  }
                </td>
              </tr>
            }
          </app-data-table>
        }
      </section>
    </ng-container>
  `,
  styles: `
    .panel-invitaciones {
      margin-top: var(--space-xl);
      display: grid;
      gap: var(--space-md);
    }
    h2 {
      margin: 0;
    }
    .formulario-invitar {
      display: flex;
      align-items: flex-end;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    .campo-select {
      display: grid;
      gap: var(--space-xs);
      min-width: 12rem;
    }
    .campo-select select {
      width: 100%;
    }
    .error {
      margin: 0;
      color: var(--danger);
      font-size: 0.875rem;
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
      flex-wrap: wrap;
    }
  `,
})
export class InvitationsPanel {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly invitaciones = signal<Invitation[]>([]);
  protected readonly roles = signal<RoleOption[]>([]);

  protected readonly email = signal('');
  protected readonly roleId = signal('');
  protected readonly errorEmail = signal<string | null>(null);
  protected readonly errorRol = signal<string | null>(null);
  protected readonly invitando = signal(false);

  protected readonly mensaje = signal<string | null>(null);
  protected readonly mensajeEsError = signal(false);
  /** `"<id>:reenviar"` o `"<id>:revocar"` mientras esa acción está en vuelo. */
  protected readonly enAccion = signal<string | null>(null);

  protected readonly columnas = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'email', label: t('admin.members.invitaciones.columnaEmail') },
      { key: 'rol', label: t('admin.members.invitaciones.columnaRol') },
      { key: 'estado', label: t('admin.members.invitaciones.columnaEstado') },
      { key: 'acciones', label: t('admin.members.invitaciones.columnaAcciones') },
    ];
  });

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const [invitaciones, roles] = await Promise.all([
        firstValueFrom(this.http.get<Invitation[]>(this.api.url('/organizations/me/invitations'))),
        firstValueFrom(this.http.get<RoleOption[]>(this.api.url('/roles'))),
      ]);
      this.invitaciones.set([...invitaciones]);
      this.roles.set([...roles]);
    } catch (error) {
      this.mostrarMensaje(error, true, 'admin.members.invitaciones.error');
    } finally {
      this.cargando.set(false);
    }
  }

  protected alElegirRol(evento: Event): void {
    this.roleId.set((evento.target as HTMLSelectElement).value);
  }

  protected tonoDe(estado: EstadoInvitacion): ChipTone {
    return TONO_POR_ESTADO[estado];
  }

  protected etiquetaDeEstado(estado: EstadoInvitacion): string {
    const claves: Record<EstadoInvitacion, string> = {
      pendiente: 'admin.members.invitaciones.estadoPendiente',
      aceptada: 'admin.members.invitaciones.estadoAceptada',
      revocada: 'admin.members.invitaciones.estadoRevocada',
      caducada: 'admin.members.invitaciones.estadoCaducada',
    };
    return this.transloco.translate(claves[estado]);
  }

  protected async invitar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.mensaje.set(null);

    const email = this.email().trim();
    this.errorEmail.set(
      !email
        ? this.transloco.translate('admin.members.invitaciones.emailRequerido')
        : !EMAIL_RE.test(email)
          ? this.transloco.translate('admin.members.invitaciones.emailInvalido')
          : null,
    );
    this.errorRol.set(
      this.roleId() ? null : this.transloco.translate('admin.members.invitaciones.rolRequerido'),
    );
    if (this.errorEmail() || this.errorRol()) {
      return;
    }

    this.invitando.set(true);
    try {
      const respuesta = await firstValueFrom(
        this.http.post<InvitationCreateResponse>(this.api.url('/organizations/me/invitations'), {
          email,
          role_id: this.roleId(),
        }),
      );
      this.email.set('');
      this.roleId.set('');
      this.mostrarMensaje(
        null,
        false,
        respuesta.status === 'added'
          ? 'admin.members.invitaciones.anadidoDirectamente'
          : 'admin.members.invitaciones.invitacionEnviada',
      );
      await this.cargar();
    } catch (error) {
      this.mostrarMensaje(error, true, 'admin.members.invitaciones.error');
    } finally {
      this.invitando.set(false);
    }
  }

  protected async reenviar(invitationId: string): Promise<void> {
    this.mensaje.set(null);
    this.enAccion.set(`${invitationId}:reenviar`);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/organizations/me/invitations/${invitationId}/resend`), {}),
      );
      this.mostrarMensaje(null, false, 'admin.members.invitaciones.reenviada');
      await this.cargar();
    } catch (error) {
      this.mostrarMensaje(error, true, 'admin.members.invitaciones.error');
    } finally {
      this.enAccion.set(null);
    }
  }

  protected async revocar(invitationId: string): Promise<void> {
    if (typeof window !== 'undefined') {
      const confirmado = window.confirm(
        this.transloco.translate('admin.members.invitaciones.confirmarRevocar'),
      );
      if (!confirmado) {
        return;
      }
    }
    this.mensaje.set(null);
    this.enAccion.set(`${invitationId}:revocar`);
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/organizations/me/invitations/${invitationId}`)),
      );
      this.mostrarMensaje(null, false, 'admin.members.invitaciones.revocada');
      await this.cargar();
    } catch (error) {
      this.mostrarMensaje(error, true, 'admin.members.invitaciones.error');
    } finally {
      this.enAccion.set(null);
    }
  }

  private mostrarMensaje(error: unknown, esError: boolean, claveDefecto: string): void {
    if (!esError) {
      this.mensajeEsError.set(false);
      this.mensaje.set(this.transloco.translate(claveDefecto));
      return;
    }
    this.mensajeEsError.set(true);
    this.mensaje.set(
      error instanceof ApiError ? error.message : this.transloco.translate(claveDefecto),
    );
  }
}
