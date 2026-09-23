import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { MarkdownSeguro } from '../../../shared/legal/markdown-seguro';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { PageHeader } from '../../../shared/ui/page-header';
import {
  type PoliticaDeOrganizacion,
  type PoliticasDeOrganizacion,
  type TipoPolitica,
} from './policies-types';
import { PolicyEditor } from './policy-editor';
import { PolicyResponsibilityNotice } from './policy-responsibility-notice';

/**
 * Textos por defecto de la organización: condiciones, reembolsos, privacidad y
 * otras. Los heredan todos sus eventos salvo que un evento los sustituya.
 * Sin `organizations:write` se ven en solo lectura.
 */
@Component({
  selector: 'app-organization-policies-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    MarkdownSeguro,
    Alert,
    Button,
    Card,
    PageHeader,
    PolicyEditor,
    PolicyResponsibilityNotice,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.politicas.rotulo')">
        {{ t('admin.politicas.tituloOrganizacion') }}
      </app-page-header>

      <app-policy-responsibility-notice />

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (errorDeCarga()) {
        <app-alert tone="error">{{ t('admin.politicas.errorCarga') }}</app-alert>
      } @else {
        @if (!puedeEditar()) {
          <app-alert tone="info">{{ t('admin.politicas.soloLectura') }}</app-alert>
        }
        @for (politica of politicas(); track politica.kind) {
          <app-card [heading]="t('admin.politicas.tipos.' + politica.kind)">
            <p class="meta">
              @if (politica.current; as actual) {
                {{ t('admin.politicas.versionGuardada', { version: actual.version }) }}
              } @else if (politica.last_version) {
                {{ t('admin.politicas.retirado') }}
              } @else {
                {{ t('admin.politicas.sinTexto') }}
              }
            </p>

            @if (puedeEditar()) {
              <app-policy-editor
                [etiqueta]="t('admin.politicas.tipos.' + politica.kind)"
                [valor]="politica.current?.content ?? ''"
                [guardando]="guardandoTipo() === politica.kind"
                [error]="errores()[politica.kind] ?? null"
                [afectaAEventoPublicado]="true"
                (guardar)="guardar(politica.kind, $event)"
              >
                @if (politica.current) {
                  <app-button
                    acciones
                    variant="secundario"
                    (pulsado)="retirando.set(politica.kind)"
                  >
                    {{ t('admin.politicas.retirar') }}
                  </app-button>
                }
              </app-policy-editor>
              @if (retirando() === politica.kind) {
                <div class="confirmar" role="alert">
                  <p>{{ t('admin.politicas.confirmarRetirar') }}</p>
                  <app-button variant="peligro" (pulsado)="retirar(politica.kind)">
                    {{ t('admin.politicas.siRetirar') }}
                  </app-button>
                  <app-button variant="terciario" (pulsado)="retirando.set(null)">
                    {{ t('comun.cancelar') }}
                  </app-button>
                </div>
              }
            } @else if (politica.current; as actual) {
              <app-markdown-seguro [texto]="actual.content" />
            }
          </app-card>
        }
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-lg);
    }
    .meta {
      margin: 0 0 var(--space-md);
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .confirmar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-sm);
      margin-top: var(--space-md);
      padding: var(--space-md);
      border: 1px solid var(--danger);
      border-radius: var(--radius-md);
    }
    .confirmar p {
      flex-basis: 100%;
      margin: 0;
    }
  `,
})
export class OrganizationPoliciesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly errorDeCarga = signal(false);
  protected readonly puedeEditar = signal(false);
  protected readonly politicas = signal<readonly PoliticaDeOrganizacion[]>([]);
  protected readonly guardandoTipo = signal<TipoPolitica | null>(null);
  protected readonly retirando = signal<TipoPolitica | null>(null);
  protected readonly errores = signal<Partial<Record<TipoPolitica, string>>>({});

  constructor() {
    void this.cargar();
  }

  private aplicar(respuesta: PoliticasDeOrganizacion): void {
    this.puedeEditar.set(respuesta.can_edit);
    this.politicas.set(respuesta.items);
  }

  private async cargar(): Promise<void> {
    try {
      this.aplicar(
        await firstValueFrom(
          this.http.get<PoliticasDeOrganizacion>(this.api.url('/organizations/me/policies')),
        ),
      );
    } catch {
      this.errorDeCarga.set(true);
    } finally {
      this.cargando.set(false);
    }
  }

  protected async guardar(kind: TipoPolitica, content: string): Promise<void> {
    this.guardandoTipo.set(kind);
    this.errores.update((actuales) => ({ ...actuales, [kind]: undefined }));
    try {
      this.aplicar(
        await firstValueFrom(
          this.http.put<PoliticasDeOrganizacion>(
            this.api.url(`/organizations/me/policies/${kind}`),
            { content },
          ),
        ),
      );
      this.retirando.set(null);
    } catch (error) {
      const mensaje =
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.politicas.errorGuardar');
      this.errores.update((actuales) => ({ ...actuales, [kind]: mensaje }));
      // Un 409 es que otra persona guardó a la vez: se recarga lo que hay.
      if (error instanceof ApiError && error.status === 409) {
        await this.cargar();
      }
    } finally {
      this.guardandoTipo.set(null);
    }
  }

  /** Retirar es guardar una versión vacía: el historial se conserva. */
  protected retirar(kind: TipoPolitica): Promise<void> {
    return this.guardar(kind, '');
  }
}
