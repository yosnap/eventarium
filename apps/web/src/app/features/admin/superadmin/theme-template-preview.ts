import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { TokensDePlantilla } from '../../../core/theming/theme-template.model';

type Modo = 'dark' | 'light';

/**
 * Miniatura de una plantilla de tema: una mini ficha de evento pintada con los
 * tokens de la plantilla en un modo concreto, con las variables CSS acotadas
 * al propio componente (`--t-*`, nunca los tokens globales) para que pueda
 * convivir con la interfaz que la rodea sin pisarla.
 *
 * La usan el catálogo de plantillas (tarjeta de selección) y el editor
 * (previsualización en vivo de lo que se está editando): mismo marcado, así
 * lo que se ve al elegir es lo que se ve al editar.
 */
@Component({
  selector: 'app-theme-template-preview',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <div
        class="escena"
        [style.--t-bg]="tokensDelModo()['bg']"
        [style.--t-surface]="tokensDelModo()['surface']"
        [style.--t-border]="tokensDelModo()['border']"
        [style.--t-fg]="tokensDelModo()['fg']"
        [style.--t-muted]="tokensDelModo()['muted']"
        [style.--t-accent]="tokensDelModo()['accent']"
        [style.--t-on-accent]="tokensDelModo()['on-accent']"
        [style.--t-font-display]="tokensDelModo()['font-display']"
        [style.--t-font-body]="tokensDelModo()['font-body']"
      >
        <article class="ficha">
          <span class="ficha-acento" aria-hidden="true"></span>
          <div class="ficha-cuerpo">
            <p class="ficha-rotulo">{{ t('admin.superadmin.plantillas.previewRotulo') }}</p>
            <h4 class="ficha-titulo">{{ t('admin.superadmin.plantillas.previewTitulo') }}</h4>
            <p class="ficha-detalles">{{ t('admin.superadmin.plantillas.previewFecha') }}</p>
            <span class="ficha-chip">{{ t('admin.superadmin.plantillas.previewChip') }}</span>
            <span class="ficha-boton">{{ t('admin.superadmin.plantillas.previewBoton') }}</span>
          </div>
        </article>
      </div>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    /* La escena aísla el tema de la plantilla: dentro manda la plantilla, fuera
       sigue mandando el panel. */
    .escena {
      background-color: var(--t-bg);
      color: var(--t-fg);
      border-radius: var(--radius-md);
      padding: var(--sp-4);
      border: 1px solid var(--border);
      /* La fuente de la plantilla manda dentro; la del panel, fuera. */
      font-family: var(--t-font-body, var(--font-body));
      min-height: 10rem;
      display: grid;
      align-content: center;
    }
    .ficha {
      background-color: var(--t-surface);
      border: 1px solid var(--t-border);
      border-radius: var(--radius-md);
      overflow: hidden;
    }
    .ficha-acento {
      display: block;
      height: 6px;
      background-color: var(--t-accent);
    }
    .ficha-cuerpo {
      padding: var(--sp-3) var(--sp-4) var(--sp-4);
      display: grid;
      gap: var(--space-xs);
    }
    .ficha-rotulo {
      margin: 0;
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--t-muted);
    }
    .ficha-titulo {
      margin: 0;
      font-family: var(--t-font-display, var(--font-display));
      font-size: 1.05rem;
      line-height: 1.25;
      color: var(--t-fg);
    }
    .ficha-detalles {
      margin: 0;
      font-size: var(--fs-sm);
      color: var(--t-muted);
    }
    .ficha-chip {
      justify-self: start;
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 2px 8px;
      border-radius: 3px;
      color: var(--t-accent);
      border: 1px solid var(--t-accent);
    }
    .ficha-boton {
      justify-self: start;
      margin-top: var(--space-xs);
      padding: 6px 14px;
      border-radius: var(--radius-sm);
      font-size: var(--fs-sm);
      font-weight: 600;
      background-color: var(--t-accent);
      color: var(--t-on-accent);
    }
  `,
})
export class ThemeTemplatePreview {
  /** Los dos modos de la plantilla (el mismo objeto `tokens` del catálogo). */
  readonly tokens = input.required<{ dark: TokensDePlantilla; light: TokensDePlantilla }>();
  /** El modo con el que pintar la escena. */
  readonly modo = input.required<Modo>();

  protected readonly tokensDelModo = computed<TokensDePlantilla>(() => this.tokens()[this.modo()]);
}
