import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Card } from '../../../../shared/ui/card';
import { Panel } from '../../../../shared/ui/panel';

/**
 * Sección «Superficies»: `app-card` y `app-panel` (envoltorio de datos, ya usado por
 * `app-data-table`). `app-panel` no tiene ranura de cabecera propia — no se añade aquí,
 * porque esta fase no modifica ese componente ya corregido — así que el rótulo va
 * fuera del panel, describiéndolo.
 */
@Component({
  selector: 'app-style-guide-superficies-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Card, Panel],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="superficies" aria-labelledby="superficies-h2">
        <div class="sec__cabecera">
          <h2 id="superficies-h2">{{ t('admin.catalogoEstilo.superficies.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.superficies.uso') }}</span>
        </div>
        <div class="cuadricula">
          <app-card [heading]="t('admin.catalogoEstilo.superficies.tarjetaTitulo')">
            <span class="rotulo-seccion">{{
              t('admin.catalogoEstilo.superficies.tarjetaRotulo')
            }}</span>
            <p>{{ t('admin.catalogoEstilo.superficies.tarjetaDescripcion') }}</p>
          </app-card>
          <div class="panel-demo">
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.superficies.panelRotulo') }}</span>
            <app-panel>
              <p class="panel-demo__texto">{{ t('admin.catalogoEstilo.superficies.panelDescripcion') }}</p>
            </app-panel>
          </div>
        </div>
        <div class="aviso-demo">
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.superficies.demoRotulo') }}</span>
          <span>{{ t('admin.catalogoEstilo.superficies.demoAviso') }}</span>
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
    .cuadricula {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
      gap: var(--space-md);
    }
    p {
      margin: 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .panel-demo {
      display: grid;
      gap: var(--space-sm);
      align-content: start;
    }
    .panel-demo__texto {
      padding: var(--space-md);
    }
    .aviso-demo {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      align-items: baseline;
      margin-top: var(--space-md);
      padding: var(--space-sm) var(--space-md);
      border: 1px dashed var(--border-strong);
      border-radius: var(--radius-sm);
      color: var(--muted);
      font-size: var(--fs-sm);
    }
  `,
})
export class SuperficiesSection {}
