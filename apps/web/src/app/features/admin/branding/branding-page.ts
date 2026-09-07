import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ThemingService } from '../../../core/theming/theming.service';
import { checkBrandingContrast } from '../../../core/theming/contrast';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

/**
 * Vista de solo lectura de la identidad visual.
 *
 * Además de mostrarla, comprueba el contraste de la paleta y avisa cuando algún par de
 * colores queda por debajo del mínimo AA: la edición llegará en una fase posterior,
 * pero el aviso ya evita publicar una web ilegible.
 */
@Component({
  selector: 'app-branding-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.branding.titulo') }}</h1>
      <p>{{ t('admin.branding.descripcion') }}</p>

      @for (aviso of avisosDeContraste(); track aviso.primero + aviso.segundo) {
        <app-alert tone="error">
          {{
            t('admin.branding.contrasteInsuficiente', {
              primero: aviso.primero,
              segundo: aviso.segundo,
              ratio: aviso.ratio,
            })
          }}
        </app-alert>
      }

      @if (theming.branding(); as branding) {
        <div class="tarjetas">
          <app-card [heading]="t('admin.branding.plantilla')">
            <p>
              <code>{{ branding.template_key }}</code>
            </p>
          </app-card>

          <app-card [heading]="t('admin.branding.logotipo')">
            @if (branding.logo_url) {
              <img [src]="branding.logo_url" [alt]="branding.organization_name" height="64" />
            } @else {
              <p>{{ t('admin.branding.sinLogotipo') }}</p>
            }
          </app-card>

          <app-card [heading]="t('admin.branding.colores')">
            <ul class="colores">
              @for (color of colores(); track color.clave) {
                <li>
                  <span
                    class="muestra"
                    [style.background-color]="color.valor"
                    aria-hidden="true"
                  ></span>
                  <code>{{ color.clave }}</code>
                  <span>{{ color.valor }}</span>
                </li>
              }
            </ul>
          </app-card>

          <app-card [heading]="t('admin.branding.tipografias')">
            <ul>
              @for (fuente of fuentes(); track fuente.clave) {
                <li>
                  <code>{{ fuente.clave }}</code
                  >: {{ fuente.valor }}
                </li>
              }
            </ul>
          </app-card>
        </div>
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
      grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
      margin-top: var(--space-lg);
    }
    ul {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: var(--space-xs);
    }
    .colores li {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .muestra {
      width: 1.5rem;
      height: 1.5rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--color-border);
    }
  `,
})
export class BrandingPage {
  protected readonly theming = inject(ThemingService);

  protected readonly colores = computed(() =>
    Object.entries(this.theming.branding()?.colors ?? {}).map(([clave, valor]) => ({
      clave,
      valor,
    })),
  );

  protected readonly fuentes = computed(() =>
    Object.entries(this.theming.branding()?.fonts ?? {}).map(([clave, valor]) => ({
      clave,
      valor,
    })),
  );

  protected readonly avisosDeContraste = computed(() =>
    checkBrandingContrast(this.theming.branding()?.colors ?? {}),
  );
}
