import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * Envoltorio de superficie para agrupar contenido con datos reales (tablas,
 * listados), replicando `.panel` de la referencia (eventarium.css:184-189).
 *
 * Sin cabecera obligatoria: la referencia separa `.panel__head`/`.panel__body`
 * para cuando hace falta un título, pero un panel sin título se usa directo,
 * como hace `app-data-table` con su contenedor de scroll (ese componente
 * proyecta su ranura de scroll dentro de `<app-panel>`, y este es quien aporta
 * el fondo/borde/radio — antes duplicados a mano dentro de `data-table.ts`).
 */
@Component({
  selector: 'app-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <ng-content />
    </div>
  `,
  styles: `
    .panel {
      background-color: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
  `,
})
export class Panel {}
