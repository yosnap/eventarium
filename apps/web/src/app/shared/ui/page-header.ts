import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Cabecera de página del panel: rótulo mono + titular a `--fs-h2` con la frase
 * clave subrayable con `.mark` + acción principal a la derecha.
 *
 * Réplica de `.head` del prototipo (`panel-organizador.html` y demás pantallas de
 * panel): flex con `space-between` alineado por la base, margen inferior `--sp-6`.
 * El titular viaja como contenido proyectado para que cada pantalla pueda marcar
 * su frase clave con `<span class="mark">…</span>` (el subrayado es global,
 * `styles.css`); el rótulo y la acción son `input`/ranura.
 */
@Component({
  selector: 'app-page-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="cabecera-pagina">
      <div>
        <p class="rotulo-seccion">{{ rotulo() }}</p>
        <h1><ng-content /></h1>
      </div>
      <div class="acciones">
        <ng-content select="[acciones]" />
      </div>
    </header>
  `,
  styles: `
    .cabecera-pagina {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-4);
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: var(--sp-6);
    }
    .rotulo-seccion {
      margin: 0;
    }
    /* El titular de página del panel pinta a --fs-h2 (no al --fs-hero público):
       el prototipo fija el tamaño inline en cada pantalla de panel; aquí queda
       fijo para todas. */
    h1 {
      font-size: var(--fs-h2);
      margin: 10px 0 0;
    }
    .acciones {
      display: flex;
      gap: var(--sp-2);
      flex-shrink: 0;
    }
    .acciones:empty {
      display: none;
    }
  `,
})
export class PageHeader {
  /** Rótulo mono en mayúsculas que abre la página («Inscripciones», «Libro del evento»). */
  readonly rotulo = input.required<string>();
}
