import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

interface MuestraColor {
  readonly token: string;
  readonly claveDescripcion: string;
}

/**
 * Sección «Color» del catálogo: una muestra por token de color del sistema, con su
 * nombre de variable y una descripción corta de uso. El fondo de cada muestra se fija
 * con `[style.background]` apuntando al propio token (`var(--token)`), nunca a un
 * color literal, así que sigue al tema activo sin duplicar ningún valor.
 */
@Component({
  selector: 'app-style-guide-color-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="color" aria-labelledby="color-h2">
        <div class="sec__cabecera">
          <h2 id="color-h2">{{ t('admin.catalogoEstilo.color.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.color.uso') }}</span>
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.color.nota1') }}</p>
        <div class="cuadricula">
          @for (muestra of muestras; track muestra.token) {
            <div class="muestra">
              <div class="muestra__color" [style.background]="'var(' + muestra.token + ')'"></div>
              <div class="muestra__texto">
                <b>{{ muestra.token }}</b>
                {{ t('admin.catalogoEstilo.color.' + muestra.claveDescripcion) }}
              </div>
            </div>
          }
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.color.nota2') }}</p>
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
    .cuadricula {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
      gap: var(--space-md);
    }
    .muestra {
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      overflow: hidden;
    }
    .muestra__color {
      height: 62px;
      border-bottom: 1px solid var(--border);
    }
    .muestra__texto {
      padding: 9px 11px;
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      color: var(--muted);
      background: var(--surface);
    }
    .muestra__texto b {
      display: block;
      color: var(--fg);
      font-weight: 400;
      margin-bottom: 3px;
    }
  `,
})
export class ColorSection {
  protected readonly muestras: readonly MuestraColor[] = [
    { token: '--bg', claveDescripcion: 'bg' },
    { token: '--surface', claveDescripcion: 'surface' },
    { token: '--surface-2', claveDescripcion: 'surface2' },
    { token: '--border', claveDescripcion: 'border' },
    { token: '--fg', claveDescripcion: 'fg' },
    { token: '--muted', claveDescripcion: 'muted' },
    { token: '--faint', claveDescripcion: 'faintDesc' },
    { token: '--accent', claveDescripcion: 'accent' },
    { token: '--warn', claveDescripcion: 'warn' },
    { token: '--danger', claveDescripcion: 'danger' },
  ];
}
