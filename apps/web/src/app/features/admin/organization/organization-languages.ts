import { ChangeDetectionStrategy, Component, computed, inject, model } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { NOMBRE_DEL_IDIOMA, type Idioma } from '../../../core/i18n/idioma';
import { ThemingService } from '../../../core/theming/theming.service';
import { Checkbox } from '../../../shared/ui/checkbox';
import { Select, type SelectOption } from '../../../shared/ui/select';

/**
 * Idiomas en que publica la organización (de los activos en la plataforma) y el
 * idioma en que escribe su contenido, que siempre está entre ellos.
 */
@Component({
  selector: 'app-organization-languages',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Checkbox, Select],
  template: `
    @if (disponibles().length > 1) {
      <fieldset *transloco="let t; prefix: 'admin.organizacion.idiomas'" class="idiomas">
        <legend>{{ t('titulo') }}</legend>
        <p class="ayuda">{{ t('ayuda') }}</p>
        @for (idioma of disponibles(); track idioma) {
          <app-checkbox
            [label]="nombre(idioma)"
            [checked]="idiomas().includes(idioma)"
            [disabled]="idioma === origen()"
            (checkedChange)="alternar(idioma, $event)"
          />
        }
        <app-select
          [label]="t('origen')"
          [hint]="t('origenAyuda')"
          [options]="opcionesDeOrigen()"
          [value]="origen()"
          (valueChange)="origen.set($any($event))"
        />
      </fieldset>
    }
  `,
  styles: `
    .idiomas {
      display: grid;
      gap: var(--space-sm);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: var(--space-md);
    }
    .ayuda {
      margin: 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
  `,
})
export class OrganizationLanguages {
  readonly idiomas = model<readonly Idioma[]>(['es-ES']);
  readonly origen = model<Idioma>('es-ES');

  private readonly theming = inject(ThemingService);
  protected readonly disponibles = computed(() => this.theming.idiomasActivos());
  protected readonly opcionesDeOrigen = computed<readonly SelectOption[]>(() =>
    this.idiomas().map((idioma) => ({ value: idioma, label: this.nombre(idioma) })),
  );

  protected nombre(idioma: Idioma): string {
    return NOMBRE_DEL_IDIOMA[idioma];
  }

  protected alternar(idioma: Idioma, marcado: boolean): void {
    const actuales = new Set(this.idiomas());
    if (marcado) {
      actuales.add(idioma);
    } else if (idioma !== this.origen()) {
      actuales.delete(idioma);
    }
    this.idiomas.set(this.disponibles().filter((disponible) => actuales.has(disponible)));
  }
}
