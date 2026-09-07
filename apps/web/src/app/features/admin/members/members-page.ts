import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { displayName } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';

interface Member {
  readonly id: string;
  readonly user_id: string;
  readonly email: string;
  readonly first_name: string | null;
  readonly last_name: string | null;
  readonly role_id: string;
  readonly role_key: string;
  readonly profile_data: Record<string, unknown>;
}

interface Page<T> {
  readonly items: readonly T[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
}

const LIMITE = 20;

/** Lista paginada de miembros de la organización, con su rol y datos de perfil. */
@Component({
  selector: 'app-members-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      <div class="cabecera">
        <div>
          <h1>{{ t('admin.members.titulo') }}</h1>
          <p>{{ t('admin.members.descripcion') }}</p>
        </div>
        <a routerLink="nuevo">
          <app-button type="button">{{ t('admin.members.anadirMiembro') }}</app-button>
        </a>
      </div>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (miembros().length === 0) {
        <p>{{ t('admin.members.sinMiembros') }}</p>
      } @else {
        <app-card>
          <table>
            <thead>
              <tr>
                <th scope="col">{{ t('admin.members.columnaNombre') }}</th>
                <th scope="col">{{ t('admin.members.columnaCorreo') }}</th>
                <th scope="col">{{ t('admin.members.columnaRol') }}</th>
              </tr>
            </thead>
            <tbody>
              @for (miembro of miembros(); track miembro.id) {
                <tr>
                  <td>{{ nombreDe(miembro) }}</td>
                  <td>{{ miembro.email }}</td>
                  <td>
                    <code>{{ miembro.role_key }}</code>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </app-card>

        @if (totalPaginas() > 1) {
          <nav [attr.aria-label]="t('admin.members.titulo')" class="paginacion">
            <app-button
              variant="secundario"
              type="button"
              [disabled]="offset() === 0"
              (pulsado)="irAPagina(offset() - limite)"
            >
              {{ t('admin.members.anterior') }}
            </app-button>
            <span>
              {{ t('admin.members.paginaDe', { actual: paginaActual(), total: totalPaginas() }) }}
            </span>
            <app-button
              variant="secundario"
              type="button"
              [disabled]="offset() + limite >= total()"
              (pulsado)="irAPagina(offset() + limite)"
            >
              {{ t('admin.members.siguiente') }}
            </app-button>
          </nav>
        }
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
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th,
    td {
      text-align: left;
      padding: var(--space-sm) var(--space-md);
      border-bottom: 1px solid var(--color-border);
    }
    .paginacion {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      margin-top: var(--space-md);
    }
  `,
})
export class MembersPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly miembros = signal<Member[]>([]);
  protected readonly total = signal(0);
  protected readonly offset = signal(0);
  protected readonly limite = LIMITE;
  protected readonly error = signal<string | null>(null);

  protected readonly totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / LIMITE)));
  protected readonly paginaActual = computed(() => Math.floor(this.offset() / LIMITE) + 1);
  protected readonly nombreDe = displayName;

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const pagina = await firstValueFrom(
        this.http.get<Page<Member>>(this.api.url('/organizations/me/members'), {
          params: { limit: LIMITE, offset: this.offset() },
        }),
      );
      this.miembros.set([...pagina.items]);
      this.total.set(pagina.total);
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.members.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected irAPagina(nuevoOffset: number): void {
    this.offset.set(Math.max(0, nuevoOffset));
    void this.cargar();
  }
}
