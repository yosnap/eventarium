import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ThemingService } from '../../../core/theming/theming.service';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { UpcomingEvents } from './upcoming-events';

/**
 * Plantilla pública «classic»: portada amplia con la marca del organizador.
 *
 * Composición sobre la referencia (`eventarium.css:129-133`, `.hero` de
 * `index.html:11-14`): titular en `--fs-hero` con la tipografía de titular (la
 * aplica el `h1` global), texto de apoyo con medida de línea acotada, y un
 * filete que cierra la sección — NO una tarjeta centrada con fondo propio, que
 * es lo que tenía esta plantilla antes y no aparece en ningún lugar del
 * prototipo.
 *
 * El rótulo y el aviso de «próximamente» que iban aquí se retiraron: decían
 * «estamos preparando la próxima edición» mientras la sección de debajo
 * listaba los eventos ya publicados. No hacía falta repetir lo que el propio
 * listado dice.
 *
 * **Aquí es donde irá el hero de verdad** cuando se decida: un bloque que
 * cuente qué es Eventarium, en vez de solo el nombre del organizador. Es una
 * pieza de producto pendiente, no un hueco que haya que rellenar con
 * decoración.
 */
@Component({
  selector: 'app-classic-template',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Reveal, UpcomingEvents],
  template: `
    <ng-container *transloco="let t">
      <section class="portada" appReveal>
        <div class="ancho-maximo portada-en">
          <h1>{{ theming.nombreDeMarca() }}</h1>
          @if (theming.organizacion()?.organizer_blurb; as descripcion) {
            <p class="descripcion">{{ descripcion }}</p>
          }
        </div>
      </section>
      <app-upcoming-events />
    </ng-container>
  `,
  styles: `
    .portada {
      border-bottom: 1px solid var(--border);
    }
    .portada-en {
      display: grid;
      gap: var(--space-md);
      padding: var(--space-xl) 0 var(--space-lg);
    }
    /* Sin max-width en ch: la referencia lo fija a 13ch para su titular fijo
       ("Un evento entero en un solo sistema"); el nombre de la organización
       es contenido dinámico de longitud variable, forzar ese ancho lo
       partiría sin motivo. */
    h1 {
      margin: 0;
    }
    .descripcion {
      margin: 0;
      max-width: 58ch;
      color: var(--muted);
    }
  `,
})
export class ClassicTemplate {
  protected readonly theming = inject(ThemingService);
}
