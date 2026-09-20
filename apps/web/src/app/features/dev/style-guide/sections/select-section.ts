import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { Select, type SelectOption } from '../../../../shared/ui/select';

/**
 * Sección «Select»: `app-select`, el select moderno de la referencia
 * (`eventarium.css:214-251`, `sistema-componentes.html#select`) — mejora progresiva
 * sobre un `<select>` nativo real, no un combobox sin equivalente en el marcado.
 * Sustituye a la sección anterior, que mostraba el `<select>` nativo suelo: el
 * propietario del producto pidió fidelidad literal con el catálogo de componentes
 * real, revirtiendo aquí la decisión de la fase 2.
 */
@Component({
  selector: 'app-style-guide-select-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Select],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="select" aria-labelledby="select-h2">
        <div class="sec__cabecera">
          <h2 id="select-h2">{{ t('admin.catalogoEstilo.select.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.select.uso') }}</span>
        </div>
        <div class="demo columna">
          <app-select
            [label]="t('admin.catalogoEstilo.select.motivo')"
            [options]="opcionesMotivo()"
            [(value)]="motivo"
          />
          <app-select
            [label]="t('admin.catalogoEstilo.select.ciudad')"
            [options]="opcionesCiudad()"
            [placeholder]="t('admin.catalogoEstilo.select.ciudadCualquiera')"
            [(value)]="ciudad"
          />
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.select.nota') }}</p>
        <p class="nota">{{ t('admin.catalogoEstilo.select.notaTeclado') }}</p>
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
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
  `,
})
export class SelectSection {
  private readonly transloco = inject(TranslocoService);

  /** Sin `placeholder`: como en un `<select>` nativo sin opción vacía, el valor
   * inicial es la primera opción («Aprender de las charlas»), no un valor vacío. */
  protected readonly motivo = signal('aprender');
  protected readonly ciudad = signal('');

  protected readonly opcionesMotivo = computed<readonly SelectOption[]>(() => [
    { value: 'aprender', label: this.t('admin.catalogoEstilo.select.motivoAprender') },
    { value: 'conocer', label: this.t('admin.catalogoEstilo.select.motivoConocer') },
    { value: 'buscar', label: this.t('admin.catalogoEstilo.select.motivoBuscar') },
    { value: 'presentar', label: this.t('admin.catalogoEstilo.select.motivoPresentar') },
  ]);

  protected readonly opcionesCiudad = computed<readonly SelectOption[]>(() => [
    { value: 'valencia', label: this.t('admin.catalogoEstilo.select.ciudadValencia') },
    { value: 'barcelona', label: this.t('admin.catalogoEstilo.select.ciudadBarcelona') },
    { value: 'online', label: this.t('admin.catalogoEstilo.select.ciudadOnline') },
  ]);

  private t(clave: string): string {
    return this.transloco.translate(clave);
  }
}
