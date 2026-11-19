import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/**
 * Bloque de carga: líneas grises con un brillo suave (quieto con «reducir
 * movimiento»). Se usa mientras se traduce un texto al idioma de la página;
 * anuncia «Traduciendo…» a los lectores de pantalla sin ocupar sitio visible.
 */
@Component({
  selector: 'app-esqueleto',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <div class="esqueleto" role="status" *transloco="let t">
      <span class="visually-hidden">{{ t('traducciones.traduciendo') }}</span>
      @for (linea of lineasArray(); track $index) {
        <span class="linea" [style.width]="linea" aria-hidden="true"></span>
      }
    </div>
  `,
  styles: `
    .esqueleto {
      display: grid;
      gap: 0.5em;
      padding-block: 0.25em;
    }
    .linea {
      display: block;
      height: 1em;
      border-radius: var(--radius-sm);
      background: linear-gradient(90deg, var(--border) 0%, var(--surface) 50%, var(--border) 100%);
      background-size: 200% 100%;
      animation: brillo 1.4s ease-in-out infinite;
    }
    @keyframes brillo {
      from {
        background-position: 100% 0;
      }
      to {
        background-position: -100% 0;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .linea {
        animation: none;
      }
    }
  `,
})
export class Esqueleto {
  /** Número de líneas; la última, más corta, como un párrafo real. */
  readonly lineas = input(1);
  protected readonly lineasArray = computed(() =>
    Array.from({ length: this.lineas() }, (_, i) =>
      i === this.lineas() - 1 && this.lineas() > 1 ? '60%' : '100%',
    ),
  );
}

/** El contenido proyectado, o un esqueleto de `lineas` mientras se traduce. */
@Component({
  selector: 'app-en-traduccion',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Esqueleto],
  template: `
    @if (traduciendo()) {
      <app-esqueleto [lineas]="lineas()" />
    } @else {
      <ng-content />
    }
  `,
  styles: `
    :host {
      display: contents;
    }
  `,
})
export class EnTraduccion {
  readonly traduciendo = input(false);
  readonly lineas = input(1);
}
