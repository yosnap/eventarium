import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Card } from '../../../../shared/ui/card';

/** Sección «Temas»: las tres lecturas del sistema (oscuro/claro/acento en claro). */
@Component({
  selector: 'app-style-guide-temas-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Card],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="temas" aria-labelledby="temas-h2">
        <div class="sec__cabecera">
          <h2 id="temas-h2">{{ t('admin.catalogoEstilo.temas.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.temas.uso') }}</span>
        </div>
        <div class="cuadricula">
          <app-card>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.temas.oscuroRotulo') }}</span>
            <h3>{{ t('admin.catalogoEstilo.temas.oscuroTitulo') }}</h3>
            <p>{{ t('admin.catalogoEstilo.temas.oscuroDescripcion') }}</p>
          </app-card>
          <app-card>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.temas.claroRotulo') }}</span>
            <h3>{{ t('admin.catalogoEstilo.temas.claroTitulo') }}</h3>
            <p>{{ t('admin.catalogoEstilo.temas.claroDescripcion') }}</p>
          </app-card>
          <app-card>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.temas.acentoRotulo') }}</span>
            <h3>{{ t('admin.catalogoEstilo.temas.acentoTitulo') }}</h3>
            <p>{{ t('admin.catalogoEstilo.temas.acentoDescripcion') }}</p>
          </app-card>
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.temas.nota') }}</p>
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
    h3 {
      margin: 10px 0 8px;
      font-size: 1.05rem;
    }
    p {
      margin: 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
  `,
})
export class TemasSection {}
