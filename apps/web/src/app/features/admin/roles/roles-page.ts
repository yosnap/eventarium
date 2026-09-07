import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';

interface RoleSummary {
  readonly id: string;
  readonly key: string;
  readonly name: string;
  readonly description: string | null;
  readonly is_system: boolean;
  readonly permissions: readonly string[];
}

/**
 * Lista de roles de la organización, con borrado de los que no son del sistema.
 *
 * El borrado pide confirmación en línea (el botón se convierte en «¿Seguro? /
 * Cancelar») en vez de un diálogo nativo, para no romper el estilo del panel ni la
 * navegación por teclado que ya tiene el resto de la interfaz.
 */
@Component({
  selector: 'app-roles-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      <div class="cabecera">
        <div>
          <h1>{{ t('admin.roles.titulo') }}</h1>
          <p>{{ t('admin.roles.descripcion') }}</p>
        </div>
        <a routerLink="nuevo">
          <app-button type="button">{{ t('admin.roles.crearRol') }}</app-button>
        </a>
      </div>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (roles().length === 0) {
        <p>{{ t('admin.roles.sinRoles') }}</p>
      } @else {
        <div class="lista">
          @for (rol of roles(); track rol.id) {
            <app-card>
              <div class="fila">
                <div>
                  <p class="nombre">
                    {{ rol.name }}
                    <span class="insignia" [class.sistema]="rol.is_system">
                      {{ rol.is_system ? t('admin.roles.sistema') : t('admin.roles.aMedida') }}
                    </span>
                  </p>
                  <p class="clave">
                    <code>{{ rol.key }}</code>
                  </p>
                  @if (rol.description) {
                    <p class="descripcion">{{ rol.description }}</p>
                  }
                </div>
                <div class="acciones">
                  <a [routerLink]="[rol.id]">
                    <app-button variant="secundario" type="button">
                      {{ t('admin.roles.editar') }}
                    </app-button>
                  </a>
                  @if (!rol.is_system) {
                    @if (pendienteDeBorrar() === rol.id) {
                      <app-button
                        variant="peligro"
                        type="button"
                        [loading]="borrando() === rol.id"
                        (pulsado)="confirmarBorrado(rol.id)"
                      >
                        {{ t('admin.roles.confirmarEliminar') }}
                      </app-button>
                      <app-button
                        variant="secundario"
                        type="button"
                        (pulsado)="pendienteDeBorrar.set(null)"
                      >
                        {{ t('admin.roles.cancelar') }}
                      </app-button>
                    } @else {
                      <app-button
                        variant="secundario"
                        type="button"
                        (pulsado)="pendienteDeBorrar.set(rol.id)"
                      >
                        {{ t('admin.roles.eliminar') }}
                      </app-button>
                    }
                  }
                </div>
              </div>
            </app-card>
          }
        </div>
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
    }
    h1 {
      margin: 0;
    }
    .lista {
      display: grid;
      gap: var(--space-md);
      margin-top: var(--space-lg);
    }
    .fila {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    .nombre {
      margin: 0;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .clave,
    .descripcion {
      margin: var(--space-xs) 0 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.875rem;
    }
    .insignia {
      font-size: 0.75rem;
      font-weight: 500;
      padding: 0.125rem 0.5rem;
      border-radius: var(--radius-sm);
      background-color: var(--color-surface-muted);
      color: var(--color-text-muted, #6b7280);
    }
    .insignia.sistema {
      background-color: var(--color-primary);
      color: var(--color-primary-contrast);
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
      flex-wrap: wrap;
    }
  `,
})
export class RolesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly roles = signal<RoleSummary[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly pendienteDeBorrar = signal<string | null>(null);
  protected readonly borrando = signal<string | null>(null);

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      this.roles.set(await firstValueFrom(this.http.get<RoleSummary[]>(this.api.url('/roles'))));
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.roles.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected async confirmarBorrado(id: string): Promise<void> {
    this.error.set(null);
    this.borrando.set(id);
    try {
      await firstValueFrom(this.http.delete(this.api.url(`/roles/${id}`)));
      this.roles.update((actuales) => actuales.filter((rol) => rol.id !== id));
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.roles.errorEliminar'),
      );
    } finally {
      this.borrando.set(null);
      this.pendienteDeBorrar.set(null);
    }
  }
}
