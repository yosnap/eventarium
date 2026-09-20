import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Input } from '../../../../shared/ui/input';
import { Textarea } from '../../../../shared/ui/textarea';

/**
 * Sección «Campos»: `app-input` normal y con error, `app-textarea`, y checkboxes
 * nativos (obligatorio/opcional) — no hay componente propio de casilla en `shared/ui`,
 * así que se usa el elemento nativo con estilos locales basados en tokens.
 */
@Component({
  selector: 'app-style-guide-campos-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Input, Textarea],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="campos" aria-labelledby="campos-h2">
        <div class="sec__cabecera">
          <h2 id="campos-h2">{{ t('admin.catalogoEstilo.campos.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.campos.uso') }}</span>
        </div>
        <div class="demo columna">
          <app-input
            [label]="t('admin.catalogoEstilo.campos.nombre')"
            [(value)]="nombre"
            [hint]="t('admin.catalogoEstilo.campos.nombrePlaceholder')"
          />
          <app-input
            [label]="t('admin.catalogoEstilo.campos.correoError')"
            type="email"
            [(value)]="correoConError"
            [error]="t('admin.catalogoEstilo.campos.correoErrorMensaje')"
          />
          <app-textarea
            [label]="t('admin.catalogoEstilo.campos.textoLargo')"
            [(value)]="textoLargo"
          />
          <label class="casilla">
            <input type="checkbox" checked />
            <span>
              {{ t('admin.catalogoEstilo.campos.consentimientoObligatorio') }}
              <span class="ayuda">{{
                t('admin.catalogoEstilo.campos.consentimientoObligatorioAyuda')
              }}</span>
            </span>
          </label>
          <label class="casilla">
            <input type="checkbox" />
            <span>
              {{ t('admin.catalogoEstilo.campos.consentimientoOpcional') }}
              <span class="ayuda">{{
                t('admin.catalogoEstilo.campos.consentimientoOpcionalAyuda')
              }}</span>
            </span>
          </label>
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
    .columna {
      display: grid;
      gap: var(--space-md);
      max-width: 32rem;
    }
    .casilla {
      display: flex;
      gap: var(--space-sm);
      align-items: flex-start;
      color: var(--fg);
    }
    .casilla input {
      margin-top: 0.2rem;
      accent-color: var(--accent);
    }
    .ayuda {
      display: block;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
  `,
})
export class CamposSection {
  protected readonly nombre = signal('');
  protected readonly correoConError = signal('ada@');
  protected readonly textoLargo = signal('');
}
