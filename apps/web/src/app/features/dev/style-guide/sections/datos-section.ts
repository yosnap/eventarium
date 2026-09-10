import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Card } from '../../../../shared/ui/card';

/**
 * Sección «Datos»: un indicador numérico grande en mono (`--fs-metric`) y un raíl de
 * nivel con `role="img"`/`aria-label` describiendo el porcentaje. Sin gráficos
 * comparativos sin dato real, y sin componentes nuevos en `shared/ui/`: ambos elementos
 * solo se usan aquí, así que van directamente dentro de `app-card` en vez de crear
 * `metric.ts`/`progress-rail.ts` sin un segundo consumidor real que justifique la
 * abstracción (YAGNI).
 */
@Component({
  selector: 'app-style-guide-datos-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Card],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="datos" aria-labelledby="datos-h2">
        <div class="sec__cabecera">
          <h2 id="datos-h2">{{ t('admin.catalogoEstilo.datos.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.datos.uso') }}</span>
        </div>
        <div class="cuadricula">
          <app-card>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.datos.indicadorRotulo') }}</span>
            <div class="indicador">{{ t('admin.catalogoEstilo.datos.indicadorValor') }}</div>
            <p class="pie">{{ t('admin.catalogoEstilo.datos.indicadorDescripcion') }}</p>
          </app-card>
          <app-card>
            <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.datos.railRotulo') }}</span>
            <div
              class="rail"
              role="img"
              [attr.aria-label]="t('admin.catalogoEstilo.datos.railEtiqueta76')"
            >
              <span class="rail__barra rail__barra--accent" style="width: 76%"></span>
            </div>
            <div
              class="rail"
              role="img"
              [attr.aria-label]="t('admin.catalogoEstilo.datos.railEtiqueta40')"
            >
              <span class="rail__barra rail__barra--muted" style="width: 40%"></span>
            </div>
            <p class="pie">{{ t('admin.catalogoEstilo.datos.railDescripcion') }}</p>
          </app-card>
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.datos.nota') }}</p>
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
    .indicador {
      font-family: var(--font-mono);
      font-size: var(--fs-metric);
      line-height: 1;
      margin-top: 10px;
    }
    .pie {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .rail {
      height: 8px;
      border: 1px solid var(--border-strong);
      border-radius: 2px;
      background: var(--bg);
      overflow: hidden;
      margin: 12px 0;
    }
    .rail__barra {
      display: block;
      height: 100%;
    }
    .rail__barra--accent {
      background: var(--accent);
    }
    .rail__barra--muted {
      background: var(--muted);
    }
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
  `,
})
export class DatosSection {}
