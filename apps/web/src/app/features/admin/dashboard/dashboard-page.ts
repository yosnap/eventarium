import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { Card } from '../../../shared/ui/card';

interface UsuarioActual {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
  readonly roles: readonly string[];
  readonly permissions: readonly string[];
}

/** Escritorio del panel: confirma quién eres y qué puedes hacer. */
@Component({
  selector: 'app-dashboard-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Card],
  template: `
    <ng-container *transloco="let t">
      @if (usuario(); as persona) {
        <h1>
          {{
            t('admin.escritorioPagina.bienvenida', { nombre: persona.full_name || persona.email })
          }}
        </h1>
        <p>{{ t('admin.escritorioPagina.resumen') }}</p>

        <div class="tarjetas">
          <app-card [heading]="t('admin.escritorioPagina.organizacion')">
            <p>{{ theming.organizationName() }}</p>
          </app-card>

          <app-card [heading]="t('admin.escritorioPagina.rolesAsignados')">
            <ul>
              @for (rol of persona.roles; track rol) {
                <li>{{ rol }}</li>
              }
            </ul>
          </app-card>

          <app-card [heading]="t('admin.escritorioPagina.permisos')">
            <ul>
              @for (permiso of persona.permissions; track permiso) {
                <li>
                  <code>{{ permiso }}</code>
                </li>
              }
            </ul>
          </app-card>
        </div>
      } @else {
        <p>{{ t('comun.cargando') }}</p>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    .tarjetas {
      display: grid;
      gap: var(--space-md);
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      margin-top: var(--space-lg);
    }
    ul {
      margin: 0;
      padding-left: 1.25rem;
    }
  `,
})
export class DashboardPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  protected readonly theming = inject(ThemingService);

  protected readonly usuario = signal<UsuarioActual | null>(null);

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.usuario.set(await firstValueFrom(this.http.get<UsuarioActual>(this.api.url('/users/me'))));
  }
}
