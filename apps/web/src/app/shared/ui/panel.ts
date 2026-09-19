import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * Envoltorio de superficie para agrupar contenido con datos reales (tablas,
 * listados), replicando `.panel` de la referencia (eventarium.css:184-189).
 *
 * Tres piezas opcionales además del contenido (que sigue siendo la ranura por
 * defecto, sin envoltorio ni padding — `app-data-table` y demás consumidores
 * existentes no cambian):
 *
 * - `[cabecera]`: franja `.panel__head` arriba (rótulo + pista o toolbar),
 *   con borde inferior. Oculta si no se proyecta nada.
 * - `[pie]`: franja de totales `.tot` abajo (contabilidad-evento.html:56-58),
 *   borde superior fuerte y fondo propio. Oculta si no se proyecta nada.
 * - Contenido no tabular que necesite el padding del cuerpo de la referencia
 *   (`.panel__body`, `--sp-5`): clase global `panel-cuerpo` en `styles.css`,
 *   porque el padding de contenido proyectado no puede venir de aquí.
 */
@Component({
  selector: 'app-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <div class="panel__head">
        <ng-content select="[cabecera]" />
      </div>
      <ng-content />
      <div class="panel__pie">
        <ng-content select="[pie]" />
      </div>
    </div>
  `,
  styles: `
    .panel {
      background-color: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
    /* .panel__head (eventarium.css:185-188). */
    .panel__head {
      display: flex;
      align-items: center;
      gap: var(--sp-3);
      flex-wrap: wrap;
      padding: var(--sp-4) var(--sp-5);
      border-bottom: 1px solid var(--border);
    }
    .panel__head:empty {
      display: none;
    }
    /* .tot (contabilidad-evento.html:56-58): pie de totales. */
    .panel__pie {
      display: flex;
      justify-content: space-between;
      gap: var(--sp-4);
      padding: 14px var(--sp-5);
      border-top: 1px solid var(--border-strong);
      background-color: var(--surface-2);
      font-size: var(--fs-sm);
    }
    .panel__pie:empty {
      display: none;
    }
    /* Los strong del pie van en mono algo mayor, como la referencia. */
    .panel__pie ::ng-deep strong {
      font-family: var(--font-mono);
      font-size: 1.05rem;
    }
  `,
})
export class Panel {}
