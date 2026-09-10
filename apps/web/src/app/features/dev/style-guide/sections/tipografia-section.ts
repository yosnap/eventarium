import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/**
 * Sección «Tipografía»: la escala completa (`--fs-h1` a `--fs-label`) con un ejemplo
 * real de cada tamaño, en la familia y el peso con que se usa en la aplicación.
 */
@Component({
  selector: 'app-style-guide-tipografia-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="tipografia" aria-labelledby="tipografia-h2">
        <div class="sec__cabecera">
          <h2 id="tipografia-h2">{{ t('admin.catalogoEstilo.tipografia.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.uso') }}</span>
        </div>
        <div class="demo escala">
          <div class="escala__item">
            <span class="h1-muestra">{{ t('admin.catalogoEstilo.tipografia.h1Muestra') }}</span>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.h1Uso') }}</span>
          </div>
          <div class="escala__item">
            <span class="h2-muestra">{{ t('admin.catalogoEstilo.tipografia.h2Muestra') }}</span>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.h2Uso') }}</span>
          </div>
          <div class="escala__item">
            <span class="h3-muestra">{{ t('admin.catalogoEstilo.tipografia.h3Muestra') }}</span>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.h3Uso') }}</span>
          </div>
          <div class="escala__item">
            <span>{{ t('admin.catalogoEstilo.tipografia.bodyMuestra') }}</span>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.bodyUso') }}</span>
          </div>
          <div class="escala__item">
            <span class="sm-muestra">{{ t('admin.catalogoEstilo.tipografia.smMuestra') }}</span>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.smUso') }}</span>
          </div>
          <div class="escala__item">
            <span class="metric-muestra">382</span>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.metricUso') }}</span>
          </div>
          <div class="escala__item">
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.labelMuestra') }}</span>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tipografia.labelUso') }}</span>
          </div>
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.tipografia.nota') }}</p>
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
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
    .demo {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--surface-2);
      padding: var(--space-md);
    }
    .escala {
      display: grid;
      gap: var(--space-md);
    }
    .escala__item {
      display: grid;
      grid-template-columns: 1fr 190px;
      gap: var(--space-md);
      align-items: baseline;
      padding-bottom: var(--space-md);
      border-bottom: 1px solid var(--border);
    }
    .escala__item:last-child {
      border-bottom: 0;
      padding-bottom: 0;
    }
    .escala__item .rotulo-seccion {
      text-align: right;
    }
    .h1-muestra {
      font-family: var(--font-display);
      font-size: var(--fs-h1);
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .h2-muestra {
      font-family: var(--font-display);
      font-size: var(--fs-h2);
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .h3-muestra {
      font-size: var(--fs-h3);
      font-weight: 500;
    }
    .sm-muestra {
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .metric-muestra {
      font-family: var(--font-mono);
      font-size: var(--fs-metric);
      line-height: 1;
    }
    @media (max-width: 860px) {
      .escala__item {
        grid-template-columns: 1fr;
      }
      .escala__item .rotulo-seccion {
        text-align: left;
      }
    }
  `,
})
export class TipografiaSection {}
