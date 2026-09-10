import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/**
 * Sección «Select»: el `<select>` nativo con los estilos globales del sistema
 * (`styles.css`). La fase 2 decidió explícitamente no construir un combobox custom:
 * esta sección muestra el control nativo tal cual, con una nota que lo deja claro.
 */
@Component({
  selector: 'app-style-guide-select-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="select" aria-labelledby="select-h2">
        <div class="sec__cabecera">
          <h2 id="select-h2">{{ t('admin.catalogoEstilo.select.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.select.uso') }}</span>
        </div>
        <div class="demo columna">
          <label class="campo">
            <span>{{ t('admin.catalogoEstilo.select.motivo') }}</span>
            <select>
              <option>{{ t('admin.catalogoEstilo.select.motivoAprender') }}</option>
              <option>{{ t('admin.catalogoEstilo.select.motivoConocer') }}</option>
              <option>{{ t('admin.catalogoEstilo.select.motivoBuscar') }}</option>
              <option>{{ t('admin.catalogoEstilo.select.motivoPresentar') }}</option>
            </select>
          </label>
          <label class="campo">
            <span>{{ t('admin.catalogoEstilo.select.ciudad') }}</span>
            <select>
              <option value="">{{ t('admin.catalogoEstilo.select.ciudadCualquiera') }}</option>
              <option>{{ t('admin.catalogoEstilo.select.ciudadValencia') }}</option>
              <option>{{ t('admin.catalogoEstilo.select.ciudadBarcelona') }}</option>
              <option>{{ t('admin.catalogoEstilo.select.ciudadOnline') }}</option>
            </select>
          </label>
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.select.nota') }}</p>
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
    .columna {
      display: grid;
      gap: var(--space-md);
      max-width: 32rem;
    }
    .campo {
      display: grid;
      gap: var(--space-xs);
      color: var(--fg);
    }
    .campo select {
      width: 100%;
    }
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
  `,
})
export class SelectSection {}
