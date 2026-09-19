import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Card } from '../../../../shared/ui/card';
import { Toggle } from '../../../../shared/ui/toggle';

/**
 * Sección «Aviso de cookies» del catálogo: el banner y la fila de categoría
 * con interruptor, tal y como los usa el banner público real
 * (`shared/cookies/cookie-banner.ts`).
 *
 * Réplica de la sección `#cookies` del prototipo
 * (`sistema-componentes.html`): banner en posición estática (el real va
 * anclado abajo), y una categoría de ejemplo con el interruptor del panel.
 */
@Component({
  selector: 'app-style-guide-cookies-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Card, Toggle],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="cookies" aria-labelledby="cookies-h2">
        <div class="sec__cabecera">
          <h2 id="cookies-h2">{{ t('admin.catalogoEstilo.cookies.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.cookies.uso') }}</span>
        </div>

        <app-card>
          <p class="nota">{{ t('admin.catalogoEstilo.cookies.notaBanner') }}</p>
          <div
            class="cookies-muestra"
            role="group"
            [attr.aria-label]="t('admin.catalogoEstilo.cookies.bannerEtiqueta')"
          >
            <p class="cookies-t">
              <strong>{{ t('admin.catalogoEstilo.cookies.bannerTitulo') }}</strong>
              {{ t('admin.catalogoEstilo.cookies.bannerTexto') }}
            </p>
            <div class="cookies-acciones">
              <button type="button" disabled>
                {{ t('admin.catalogoEstilo.cookies.soloNecesarias') }}
              </button>
              <button type="button" disabled>
                {{ t('admin.catalogoEstilo.cookies.aceptarTodas') }}
              </button>
              <button type="button" disabled>{{ t('admin.catalogoEstilo.cookies.elegir') }}</button>
            </div>
          </div>
        </app-card>

        <app-card>
          <span class="rotulo-seccion">{{
            t('admin.catalogoEstilo.cookies.categoriaRotulo')
          }}</span>
          <app-toggle
            [label]="t('admin.catalogoEstilo.cookies.medicion')"
            [estado]="t('admin.catalogoEstilo.cookies.si')"
            [hint]="t('admin.catalogoEstilo.cookies.medicionHint')"
            [checked]="true"
          />
          <p class="nota">{{ t('admin.catalogoEstilo.cookies.notaInterruptor') }}</p>
        </app-card>
      </section>
    </ng-container>
  `,
  styles: `
    .nota {
      margin: 0 0 var(--space-md);
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .nota:last-child {
      margin: var(--space-md) 0 0;
    }
    /* La muestra del banner, en estático: el real va anclado abajo con
       position:fixed (cookie-banner.ts), aquí solo se enseña el patrón. */
    /* Mismos tokens que el banner real (cookie-banner.ts): surface y borde
       fuerte, no los genéricos. */
    .cookies-muestra {
      display: grid;
      gap: var(--space-md);
      padding: var(--space-lg);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface);
    }
    .cookies-t {
      margin: 0;
    }
    .cookies-acciones {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    /* Botones deshabilitados: la muestra enseña la forma real del control
       sin que nada sea clicable en el catálogo. */
    .cookies-acciones button {
      display: inline-flex;
      align-items: center;
      padding: 0 1.25rem;
      min-height: 2.75rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-strong);
      color: var(--fg);
      font-size: var(--fs-sm);
      background-color: transparent;
      cursor: default;
    }
  `,
})
export class CookiesSection {}
