import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  inject,
  input,
  makeStateKey,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiService } from '../../../core/api/api.service';
import {
  type PoliticasPublicas,
  PublicPoliciesService,
} from '../../../core/policies/public-policies.service';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { MarkdownSeguro } from '../../../shared/legal/markdown-seguro';
import { Alert } from '../../../shared/ui/alert';

/**
 * Políticas y condiciones de un evento, tal como las fija su organizador.
 *
 * Mismo patrón que `legal-page.ts`: se resuelven en SSR, viajan al cliente por
 * `TransferState` y el Markdown lo pinta `<app-markdown-seguro>` (texto plano
 * en el servidor, saneado tras hidratar). Cada documento lleva un ancla
 * (`#condiciones`, `#reembolsos`, `#privacidad`, `#otras`) para enlazarlo
 * desde el formulario de inscripción.
 */
@Component({
  selector: 'app-public-policies-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, DatePipe, MarkdownSeguro, Alert],
  template: `
    <ng-container *transloco="let t">
      <div class="ancho-maximo">
        <p class="volver">
          <a [routerLink]="['/eventos', slug()]">← {{ t('comun.volver') }}</a>
        </p>
        <h1>{{ t('publico.politicas.titulo') }}</h1>

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (error()) {
          <app-alert tone="error">{{ t('publico.politicas.error') }}</app-alert>
        } @else if (datos(); as d) {
          @if (d.policies.length === 0) {
            <p>{{ t('publico.politicas.sinTextos') }}</p>
            <p>
              <a routerLink="/legal/condiciones-de-inscripcion">
                {{ t('publico.politicas.generales') }}
              </a>
            </p>
          } @else {
            @for (politica of d.policies; track politica.version_id) {
              <section class="politica" [id]="politica.kind">
                <h2>{{ t('publico.politicas.tipos.' + politica.kind) }}</h2>
                <p class="fecha">
                  {{
                    t('publico.politicas.fecha', {
                      version: politica.version,
                      fecha: politica.created_at | date: 'longDate',
                    })
                  }}
                </p>
                <app-markdown-seguro [texto]="politica.content" />
              </section>
            }
            <p class="pie">
              {{ t('publico.politicas.pie', { organizacion: d.organization_name }) }}
            </p>
          }
        }
      </div>
    </ng-container>
  `,
  styles: `
    .ancho-maximo {
      padding: var(--space-lg) 0;
    }
    .volver {
      margin: 0 0 var(--space-md);
      font-size: var(--fs-sm);
    }
    h1 {
      margin-top: 0;
    }
    .politica {
      margin-top: var(--space-lg);
      scroll-margin-top: 5rem;
    }
    .fecha,
    .pie {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .pie {
      margin-top: var(--space-lg);
    }
  `,
})
export class PublicPoliciesPage implements OnInit {
  readonly slug = input.required<string>();

  private readonly servicio = inject(PublicPoliciesService);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly transloco = inject(TranslocoService);

  protected readonly datos = signal<PoliticasPublicas | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal(false);

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PoliticasPublicas>(`politicas-evento:${this.slug()}`);
    const transferido = this.transferState.get(clave, null);
    try {
      const datos = transferido ?? (await this.servicio.obtener(this.slug()));
      if (transferido) {
        this.transferState.remove(clave);
      } else if (this.api.isServer) {
        this.transferState.set(clave, datos);
      }
      this.datos.set(datos);
      this.seo.set({ title: this.transloco.translate('publico.politicas.titulo') });
    } catch {
      this.error.set(true);
    } finally {
      this.cargando.set(false);
    }
  }
}
