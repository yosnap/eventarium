import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { IdiomaService } from '../../core/i18n/idioma.service';

/**
 * Nota discreta cuando el contenido del organizador se muestra en su idioma
 * original porque todavía no está traducido al idioma de la página.
 * `servido` es el `served_locale` de la respuesta de la API.
 */
@Component({
  selector: 'app-aviso-contenido-original',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    @if (visible()) {
      <p *transloco="let t" class="aviso" role="note">{{ t('publico.contenidoOriginal') }}</p>
    }
  `,
  styles: `
    .aviso {
      margin: 0;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
  `,
})
export class AvisoContenidoOriginal {
  readonly servido = input<string | null | undefined>(undefined);
  private readonly idioma = inject(IdiomaService).idioma();

  protected readonly visible = computed(() => {
    const servido = this.servido();
    return !!servido && servido !== this.idioma;
  });
}
