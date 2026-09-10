import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/**
 * Sección «Fondo y realce»: geometría de la retícula de fondo (`body::before` en
 * `styles.css`) ampliada y con el contraste realzado para que se aprecie en una caja
 * pequeña, más el subrayado `.mark` sobre un dato clave.
 *
 * La muestra usa `var(--border-strong)`, un token ya existente y más opaco que
 * `--grid-line`, en vez de declarar un color nuevo solo para este realce: mismo efecto
 * visual, ningún literal de color añadido.
 *
 * Sin `data-reveal`/animación de entrada: la fase 2 decidió explícitamente no construir
 * directivas de revelado ni animación de scroll, así que esa parte de la referencia
 * queda fuera; solo se replica la geometría visual estática.
 */
@Component({
  selector: 'app-style-guide-fondo-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="fondo" aria-labelledby="fondo-h2">
        <div class="sec__cabecera">
          <h2 id="fondo-h2">{{ t('admin.catalogoEstilo.fondo.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.fondo.uso') }}</span>
        </div>
        <div class="reticula-demo" role="img" [attr.aria-label]="t('admin.catalogoEstilo.fondo.retriculaEtiqueta')"></div>
        <p class="nota">{{ t('admin.catalogoEstilo.fondo.retriculaNota') }}</p>
        <div class="demo">
          <p>
            {{ t('admin.catalogoEstilo.fondo.marcaTexto') }}
            <span class="mark">{{ t('admin.catalogoEstilo.fondo.marcaResaltado') }}</span>
            {{ t('admin.catalogoEstilo.fondo.marcaFin') }}
          </p>
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
    .reticula-demo {
      height: 140px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background:
        linear-gradient(var(--border-strong) 1px, transparent 1px) 0 0 / 100% var(--grid-size),
        linear-gradient(90deg, var(--border-strong) 1px, transparent 1px) 0 0 / var(--grid-size)
          100%,
        var(--bg);
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
      margin-top: var(--space-md);
    }
    .demo p {
      margin: 0;
    }
  `,
})
export class FondoSection {}
