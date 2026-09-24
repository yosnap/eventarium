import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, type OnInit, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Chip } from '../../../shared/ui/chip';
import { PageHeader } from '../../../shared/ui/page-header';
import { McpKeyForm } from './mcp-key-form';

export interface ConexionMcp {
  readonly id: string;
  readonly name: string;
  readonly method: string;
  readonly scopes: readonly string[];
  readonly event_ids: readonly string[] | null;
  readonly key_prefix: string | null;
  readonly created_at: string;
  readonly expires_at: string;
  readonly last_used_at: string | null;
  readonly revoked_at: string | null;
  /** Solo en el listado de la organización. */
  readonly user_email?: string;
}

const MIAS = '/users/me/mcp-connections';
const DE_LA_ORGANIZACION = '/organizations/me/mcp-connections';

/**
 * Conectar asistentes (Claude, ChatGPT, Cursor, bots) por MCP con la cuenta
 * de la persona. Sin estado de permisos en el cliente: si la API responde 403
 * a «mis conexiones», falta `mcp:connect` y se explica cómo pedirlo; si lo
 * responde al listado de la organización, no es el dueño y ese bloque no sale.
 */
@Component({
  selector: 'app-mcp-connections-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, DatePipe, Alert, Button, Card, Chip, PageHeader, McpKeyForm],
  template: `
    <ng-container *transloco="let t; read: 'admin.mcp'">
      <app-page-header [rotulo]="t('rotulo')">{{ t('titulo') }}</app-page-header>

      @if (sinPermiso()) {
        <app-alert tone="info" [title]="t('sinPermisoTitulo')">{{ t('sinPermiso') }}</app-alert>
      } @else {
        <app-card [heading]="t('comoConectar')">
          <p>{{ t('comoConectarTexto') }}</p>
          <p>
            <code>{{ urlMcp }}</code>
          </p>
          <ul>
            <li>{{ t('clienteClaude') }}</li>
            <li>{{ t('clienteChatgpt') }}</li>
            <li>{{ t('clienteCursor') }}</li>
          </ul>
        </app-card>

        <app-mcp-key-form (creadaUna)="cargarMias()" />

        <app-card [heading]="t('mias')">
          @if (mias().length === 0) {
            <p>{{ t('sinConexiones') }}</p>
          } @else {
            <ul class="conexiones">
              @for (c of mias(); track c.id) {
                <li>
                  <div>
                    <strong>{{ c.name }}</strong>
                    @if (c.revoked_at) {
                      <app-chip tone="apagado">{{ t('revocada') }}</app-chip>
                    }
                    <p class="detalle">
                      {{ c.scopes.join(', ') }} ·
                      {{
                        c.event_ids ? t('eventosConcretos', { n: c.event_ids.length }) : t('todos')
                      }}
                    </p>
                    <p class="detalle">
                      {{ t('caduca') }} {{ c.expires_at | date: 'd MMM y' }} ·
                      {{
                        c.last_used_at
                          ? t('ultimoUso') + ' ' + (c.last_used_at | date: 'd MMM y, HH:mm')
                          : t('sinUso')
                      }}
                    </p>
                  </div>
                  @if (!c.revoked_at) {
                    <app-button type="button" variant="peligro" (pulsado)="revocar(c, false)">
                      {{ t('revocar') }}<span class="sr-only"> {{ c.name }}</span>
                    </app-button>
                  }
                </li>
              }
            </ul>
          }
        </app-card>
      }

      @if (esDueno()) {
        <app-card [heading]="t('deLaOrganizacion')">
          <p>{{ t('deLaOrganizacionTexto') }}</p>
          @if (deLaOrganizacion().length === 0) {
            <p>{{ t('sinConexiones') }}</p>
          } @else {
            <ul class="conexiones">
              @for (c of deLaOrganizacion(); track c.id) {
                <li>
                  <div>
                    <strong>{{ c.name }}</strong> · {{ c.user_email }}
                    @if (c.revoked_at) {
                      <app-chip tone="apagado">{{ t('revocada') }}</app-chip>
                    }
                    <p class="detalle">{{ c.scopes.join(', ') }}</p>
                  </div>
                  @if (!c.revoked_at) {
                    <app-button type="button" variant="peligro" (pulsado)="revocar(c, true)">
                      {{ t('revocar') }}<span class="sr-only"> {{ c.name }}</span>
                    </app-button>
                  }
                </li>
              }
            </ul>
          }
        </app-card>
      }

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-lg);
    }
    .conexiones {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--sp-4);
    }
    .conexiones li {
      display: flex;
      justify-content: space-between;
      gap: var(--sp-4);
      align-items: flex-start;
      border-bottom: 1px solid var(--border);
      padding-bottom: var(--sp-4);
    }
    .detalle {
      margin: var(--sp-1) 0 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    code {
      font-family: var(--font-mono);
      word-break: break-all;
    }
  `,
})
export class McpConnectionsPage implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly urlMcp = `${globalThis.location?.origin ?? ''}/mcp`;
  protected readonly mias = signal<readonly ConexionMcp[]>([]);
  protected readonly deLaOrganizacion = signal<readonly ConexionMcp[]>([]);
  protected readonly sinPermiso = signal(false);
  protected readonly esDueno = signal(false);
  protected readonly error = signal<string | null>(null);

  ngOnInit(): void {
    void this.cargarMias();
    void this.cargarDeLaOrganizacion();
  }

  async cargarMias(): Promise<void> {
    try {
      this.mias.set(await firstValueFrom(this.http.get<ConexionMcp[]>(this.api.url(MIAS))));
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        this.sinPermiso.set(true);
      } else {
        this.error.set(this.mensaje(error));
      }
    }
  }

  private async cargarDeLaOrganizacion(): Promise<void> {
    try {
      this.deLaOrganizacion.set(
        await firstValueFrom(this.http.get<ConexionMcp[]>(this.api.url(DE_LA_ORGANIZACION))),
      );
      this.esDueno.set(true);
    } catch {
      // 403 = no es el dueño: ese bloque no se enseña.
      this.esDueno.set(false);
    }
  }

  protected async revocar(conexion: ConexionMcp, comoDueno: boolean): Promise<void> {
    this.error.set(null);
    const base = comoDueno ? DE_LA_ORGANIZACION : MIAS;
    try {
      await firstValueFrom(this.http.delete(this.api.url(`${base}/${conexion.id}`)));
      await Promise.all([this.cargarMias(), this.esDueno() ? this.cargarDeLaOrganizacion() : null]);
    } catch (error) {
      this.error.set(this.mensaje(error));
    }
  }

  private mensaje(error: unknown): string {
    return error instanceof ApiError ? error.message : this.transloco.translate('admin.mcp.error');
  }
}
