import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from '../../../../shared/ui/button';

/**
 * Sección «Estados»: reposo, hover, foco visible y deshabilitado del botón, fijados
 * visualmente para verlos sin interactuar.
 *
 * `app-button` no expone una entrada para forzar su estado interno de hover/foco, y
 * esta fase no toca ese componente ya corregido. La solución más simple sin tocarlo:
 * envolver cada muestra en un contenedor con una clase de demo local
 * (`.forzar-hover`/`.forzar-foco`) y usar `::ng-deep` para pintar el `<button>` que
 * `app-button` renderiza dentro, replicando exactamente la regla que ese componente ya
 * aplica en `:hover`/`:focus-visible`.
 */
@Component({
  selector: 'app-style-guide-estados-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="estados" aria-labelledby="estados-h2">
        <div class="sec__cabecera">
          <h2 id="estados-h2">{{ t('admin.catalogoEstilo.estados.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.estados.uso') }}</span>
        </div>
        <div class="estados">
          <div class="estado">
            <span class="rotulo-seccion etiqueta">{{ t('admin.catalogoEstilo.estados.reposo') }}</span>
            <app-button variant="primario">{{ t('admin.catalogoEstilo.estados.accion') }}</app-button>
          </div>
          <div class="estado forzar-hover">
            <span class="rotulo-seccion etiqueta">{{ t('admin.catalogoEstilo.estados.hover') }}</span>
            <app-button variant="primario">{{ t('admin.catalogoEstilo.estados.accion') }}</app-button>
          </div>
          <div class="estado forzar-foco">
            <span class="rotulo-seccion etiqueta">{{ t('admin.catalogoEstilo.estados.foco') }}</span>
            <app-button variant="primario">{{ t('admin.catalogoEstilo.estados.accion') }}</app-button>
          </div>
          <div class="estado">
            <span class="rotulo-seccion etiqueta">{{
              t('admin.catalogoEstilo.estados.deshabilitado')
            }}</span>
            <app-button variant="primario" [disabled]="true">{{
              t('admin.catalogoEstilo.estados.accion')
            }}</app-button>
          </div>
          <div class="estado">
            <span class="rotulo-seccion etiqueta">{{
              t('admin.catalogoEstilo.estados.secundarioReposo')
            }}</span>
            <app-button variant="secundario">{{
              t('admin.catalogoEstilo.estados.accionSecundaria')
            }}</app-button>
          </div>
          <div class="estado forzar-hover">
            <span class="rotulo-seccion etiqueta">{{
              t('admin.catalogoEstilo.estados.secundarioHover')
            }}</span>
            <app-button variant="secundario">{{
              t('admin.catalogoEstilo.estados.accionSecundaria')
            }}</app-button>
          </div>
        </div>
        <p class="nota">{{ t('admin.catalogoEstilo.estados.nota') }}</p>
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
    .estados {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
      gap: var(--space-md);
    }
    .estado {
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: var(--space-md);
      background: var(--surface);
    }
    .etiqueta {
      display: block;
      margin-bottom: 10px;
    }
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
    /* Estados forzados: reproducen la misma regla que app-button ya aplica en
       :hover/:focus-visible, solo que fijada por clase en vez de por interacción.
       :host ::ng-deep, no ::ng-deep a secas (mismo motivo que data-table.ts): sin el
       :host el selector compilaría sin atributo de encapsulación y pintaría cualquier
       botón de la aplicación, no solo los de esta sección de demo. */
    :host ::ng-deep .forzar-hover button.primario {
      background-color: var(--accent-hi);
      color: var(--on-accent);
    }
    :host ::ng-deep .forzar-hover button.secundario {
      background-color: var(--surface-hi);
      border-color: var(--faint);
    }
    :host ::ng-deep .forzar-foco button {
      outline: 3px solid var(--accent);
      outline-offset: 2px;
    }
  `,
})
export class EstadosSection {}
