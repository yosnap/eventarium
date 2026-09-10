import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Chip } from '../../../../shared/ui/chip';

/** Sección «Chips de estado»: los cuatro tonos de `app-chip`. */
@Component({
  selector: 'app-style-guide-chips-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Chip],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="chips" aria-labelledby="chips-h2">
        <div class="sec__cabecera">
          <h2 id="chips-h2">{{ t('admin.catalogoEstilo.chips.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.chips.uso') }}</span>
        </div>
        <div class="demo">
          <div class="fila">
            <app-chip tone="neutro">{{ t('admin.catalogoEstilo.chips.neutro') }}</app-chip>
            <app-chip tone="ok">{{ t('admin.catalogoEstilo.chips.ok') }}</app-chip>
            <app-chip tone="espera">{{ t('admin.catalogoEstilo.chips.espera') }}</app-chip>
            <app-chip tone="apagado">{{ t('admin.catalogoEstilo.chips.apagado') }}</app-chip>
          </div>
          <p class="nota">{{ t('admin.catalogoEstilo.chips.nota') }}</p>
        </div>
      </section>
    </ng-container>
  `,
  styles: `
    .sec__cabecera {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-md);
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: var(--space-md);
    }
    h2 {
      margin: 0;
      font-family: var(--font-body);
      font-size: var(--fs-h3);
      font-weight: 500;
    }
    .demo {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--surface-2);
      padding: var(--space-md);
    }
    .fila {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      align-items: center;
    }
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
  `,
})
export class ChipsSection {}
