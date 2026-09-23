import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { MarkdownSeguro } from '../../../shared/legal/markdown-seguro';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { type AcceptedPolicyOut } from '../events/registration-types';
import { type VersionDePolitica } from './policies-types';

/**
 * Lo que aceptó una inscripción de las políticas del organizador, con acceso
 * al texto exacto de cada versión: es la prueba ante una reclamación, aunque
 * el texto se haya cambiado después.
 */
@Component({
  selector: 'app-accepted-policies',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, DatePipe, MarkdownSeguro, Alert, Button],
  template: `
    <ng-container *transloco="let t">
      <div class="politicas">
        @if (aceptadasEl(); as fecha) {
          <p class="titulo">
            {{ t('admin.events.registrations.detalle.politicasAceptadas') }}:
            {{ fecha | date: 'medium' }}
          </p>
          <ul>
            @for (version of versiones(); track version.version_id) {
              <li>
                <app-button variant="terciario" [compacto]="true" (pulsado)="alternar(version)">
                  {{
                    abierta()?.version_id === version.version_id
                      ? t('admin.events.registrations.detalle.ocultarVersion')
                      : t('admin.events.registrations.detalle.verVersion', {
                          tipo: t('admin.politicas.tipos.' + version.kind),
                          version: version.version,
                        })
                  }}
                </app-button>
                @if (abierta()?.version_id === version.version_id) {
                  @if (contenido(); as texto) {
                    <app-markdown-seguro class="texto" [texto]="texto.content" />
                  } @else if (error()) {
                    <app-alert tone="error">
                      {{ t('admin.events.registrations.detalle.errorVersion') }}
                    </app-alert>
                  }
                }
              </li>
            }
          </ul>
        } @else {
          <p class="titulo">{{ t('admin.events.registrations.detalle.politicasNoAplica') }}</p>
        }
      </div>
    </ng-container>
  `,
  styles: `
    .politicas {
      margin-top: var(--space-md);
    }
    .titulo {
      margin: 0 0 var(--space-sm);
      font-size: var(--fs-sm);
    }
    ul {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-xs);
    }
    .texto {
      margin: var(--space-sm) 0 var(--space-md);
      padding: var(--space-md);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
  `,
})
export class AcceptedPolicies {
  readonly eventId = input.required<string>();
  readonly aceptadasEl = input<string | null>(null);
  readonly versiones = input<readonly AcceptedPolicyOut[]>([]);

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  protected readonly abierta = signal<AcceptedPolicyOut | null>(null);
  protected readonly contenido = signal<VersionDePolitica | null>(null);
  protected readonly error = signal(false);

  protected async alternar(version: AcceptedPolicyOut): Promise<void> {
    if (this.abierta()?.version_id === version.version_id) {
      this.abierta.set(null);
      return;
    }
    this.abierta.set(version);
    this.contenido.set(null);
    this.error.set(false);
    try {
      this.contenido.set(
        await firstValueFrom(
          this.http.get<VersionDePolitica>(
            this.api.url(`/events/${this.eventId()}/policies/versions/${version.version_id}`),
          ),
        ),
      );
    } catch {
      this.error.set(true);
    }
  }
}
