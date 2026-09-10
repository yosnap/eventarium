import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from '../../../../shared/ui/button';

/** Sección «Botones»: las seis variantes/modificadores de `app-button`. */
@Component({
  selector: 'app-style-guide-botones-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="botones" aria-labelledby="botones-h2">
        <div class="sec__cabecera">
          <h2 id="botones-h2">{{ t('admin.catalogoEstilo.botones.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.botones.uso') }}</span>
        </div>
        <div class="demo">
          <span class="rotulo-seccion etiqueta-demo">{{
            t('admin.catalogoEstilo.botones.muestra')
          }}</span>
          <div class="fila">
            <app-button variant="primario">{{ t('admin.catalogoEstilo.botones.primario') }}</app-button>
            <app-button variant="secundario">{{
              t('admin.catalogoEstilo.botones.secundario')
            }}</app-button>
            <app-button variant="terciario">{{
              t('admin.catalogoEstilo.botones.terciario')
            }}</app-button>
            <app-button variant="peligro">{{ t('admin.catalogoEstilo.botones.peligro') }}</app-button>
            <app-button variant="secundario" [compacto]="true">{{
              t('admin.catalogoEstilo.botones.compacto')
            }}</app-button>
            <app-button variant="secundario" [disabled]="true">{{
              t('admin.catalogoEstilo.botones.deshabilitado')
            }}</app-button>
          </div>
          <p class="nota">{{ t('admin.catalogoEstilo.botones.nota') }}</p>
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
    .etiqueta-demo {
      display: block;
      margin-bottom: var(--space-md);
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
export class BotonesSection {}
