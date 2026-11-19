import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { NOMBRE_DEL_IDIOMA, type Idioma } from '../../../core/i18n/idioma';
import {
  type ResumenDeTraduccion,
  TraduccionesService,
} from '../../../core/traducciones/traducciones.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { AvisoClavePropia } from '../../../shared/ui/aviso-clave-propia';
import { Card } from '../../../shared/ui/card';

/** «English: 12/14 textos al día» en la ficha del evento, por cada idioma. */
@Component({
  selector: 'app-event-translation-summary',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AvisoClavePropia, Card],
  template: `
    @if (resumen(); as r) {
      @if (r.locales.length > 0) {
        <app-card *transloco="let t; prefix: 'traducciones.resumen'" [heading]="t('titulo')">
          <ul>
            @for (idioma of r.locales; track idioma.locale) {
              <li>
                {{
                  t('linea', {
                    idioma: nombre(idioma.locale),
                    al_dia: idioma.up_to_date,
                    total: idioma.total,
                  })
                }}
              </li>
            }
          </ul>
          <p class="ayuda">{{ t('ayuda') }}</p>
          @if (r.auto_translation_available === false) {
            <app-aviso-clave-propia />
          }
        </app-card>
      }
    }
  `,
  styles: `
    ul {
      margin: 0;
      padding-left: var(--space-md);
    }
    .ayuda {
      margin: var(--space-xs) 0 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
  `,
})
export class EventTranslationSummary {
  readonly eventId = input.required<string>();

  private readonly servicio = inject(TraduccionesService);
  private readonly theming = inject(ThemingService);
  protected readonly resumen = signal<ResumenDeTraduccion | null>(null);

  constructor() {
    effect(() => {
      const id = this.eventId();
      // Con un solo idioma en la plataforma no hay nada que resumir.
      const varios = (this.theming.plataforma()?.enabled_locales?.length ?? 0) > 1;
      untracked(() => (varios ? void this.cargar(id) : this.resumen.set(null)));
    });
  }

  protected nombre(idioma: Idioma): string {
    return NOMBRE_DEL_IDIOMA[idioma];
  }

  private async cargar(id: string): Promise<void> {
    try {
      this.resumen.set(await this.servicio.resumenDeEvento(id));
    } catch {
      // Sin permiso o sin conexión: la ficha sigue sin el resumen.
      this.resumen.set(null);
    }
  }
}
