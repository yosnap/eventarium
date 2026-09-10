import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { BotonesSection } from './sections/botones-section';
import { CamposSection } from './sections/campos-section';
import { ChipsSection } from './sections/chips-section';
import { ColorSection } from './sections/color-section';
import { DatosSection } from './sections/datos-section';
import { EstadosSection } from './sections/estados-section';
import { FondoSection } from './sections/fondo-section';
import { SelectSection } from './sections/select-section';
import { SuperficiesSection } from './sections/superficies-section';
import { TablasSection } from './sections/tablas-section';
import { TemasSection } from './sections/temas-section';
import { TipografiaSection } from './sections/tipografia-section';

interface EntradaIndice {
  readonly href: string;
  readonly claveTexto: string;
}

/**
 * Réplica del prototipo real `sistema-componentes.html`: el catálogo interno de
 * `shared/ui`, sección por sección y en el mismo orden, con un índice lateral pegajoso
 * de enlaces ancla. Cada sección vive en su propio componente bajo `./sections/` para
 * mantener este fichero corto y cada pieza enfocada en un único bloque del prototipo.
 *
 * Réplica completa a propósito, aunque alguna sección (p. ej. Color, Tipografía,
 * Estados, Fondo, Temas) no tenga hoy un consumidor real fuera de esta página: así lo
 * pidió el propietario del producto, sustituyendo la decisión de descarte de una fase
 * anterior para el resto de la aplicación — esa decisión no aplica a este catálogo.
 *
 * No es una pantalla de producto: vive dentro de `admin/estilo` (autenticado). Sí entra
 * en la suite de axe (`style-guide-page.spec.ts`): reúne todos los componentes a la
 * vez, así que es donde antes se detecta una regresión de contraste.
 *
 * Sin conmutador de tema propio: reutiliza el de `AdminShell`. Sin `<main>` propio: ese
 * landmark ya lo pone `AdminShell` alrededor de `<router-outlet>`.
 */
@Component({
  selector: 'app-style-guide-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    ColorSection,
    TipografiaSection,
    BotonesSection,
    EstadosSection,
    ChipsSection,
    CamposSection,
    SelectSection,
    SuperficiesSection,
    DatosSection,
    TablasSection,
    FondoSection,
    TemasSection,
  ],
  template: `
    <ng-container *transloco="let t">
      <div class="cabecera-pagina">
        <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.titulo') }}</span>
        <h1>{{ t('admin.catalogoEstilo.encabezado') }}</h1>
        <p class="introduccion">{{ t('admin.catalogoEstilo.introduccion') }}</p>
      </div>

      <div class="armazon">
        <nav class="indice" [attr.aria-label]="t('admin.catalogoEstilo.indice')">
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.indiceRotulo') }}</span>
          <ol>
            @for (entrada of indice; track entrada.href) {
              <li><a [href]="entrada.href">{{ t(entrada.claveTexto) }}</a></li>
            }
          </ol>
        </nav>

        <div class="secciones">
          <app-style-guide-color-section />
          <app-style-guide-tipografia-section />
          <app-style-guide-botones-section />
          <app-style-guide-estados-section />
          <app-style-guide-chips-section />
          <app-style-guide-campos-section />
          <app-style-guide-select-section />
          <app-style-guide-superficies-section />
          <app-style-guide-datos-section />
          <app-style-guide-tablas-section />
          <app-style-guide-fondo-section />
          <app-style-guide-temas-section />
        </div>
      </div>
    </ng-container>
  `,
  styles: `
    .cabecera-pagina {
      margin-bottom: var(--space-lg);
    }
    h1 {
      margin: 12px 0 0;
      max-width: 20ch;
    }
    .introduccion {
      max-width: 62ch;
      margin-top: var(--space-md);
      color: var(--muted);
    }
    .armazon {
      display: grid;
      grid-template-columns: 210px minmax(0, 1fr);
      gap: var(--space-lg);
    }
    .indice {
      position: sticky;
      top: 5rem;
      align-self: start;
    }
    .indice ol {
      list-style: none;
      margin: var(--space-sm) 0 0;
      padding: 0;
      display: grid;
      gap: 1px;
    }
    .indice a {
      display: block;
      min-height: 34px;
      padding: 7px 11px;
      border-radius: var(--radius-sm);
      text-decoration: none;
      font-size: var(--fs-sm);
      color: var(--muted);
      transition:
        background-color 0.15s,
        color 0.15s;
    }
    .indice a:hover {
      background: var(--surface-hi);
      color: var(--fg);
    }
    .secciones > * {
      display: block;
      padding-bottom: var(--space-lg);
      margin-bottom: var(--space-lg);
      border-bottom: 1px solid var(--border);
    }
    .secciones > *:last-child {
      border-bottom: 0;
      margin-bottom: 0;
      padding-bottom: 0;
    }
    @media (max-width: 860px) {
      .armazon {
        grid-template-columns: 1fr;
        gap: var(--space-md);
      }
      .indice {
        position: static;
      }
      .indice ol {
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      }
    }
  `,
})
export class StyleGuidePage {
  protected readonly indice: readonly EntradaIndice[] = [
    { href: '#color', claveTexto: 'admin.catalogoEstilo.color.titulo' },
    { href: '#tipografia', claveTexto: 'admin.catalogoEstilo.tipografia.titulo' },
    { href: '#botones', claveTexto: 'admin.catalogoEstilo.botones.titulo' },
    { href: '#estados', claveTexto: 'admin.catalogoEstilo.estados.titulo' },
    { href: '#chips', claveTexto: 'admin.catalogoEstilo.chips.titulo' },
    { href: '#campos', claveTexto: 'admin.catalogoEstilo.campos.titulo' },
    { href: '#select', claveTexto: 'admin.catalogoEstilo.select.titulo' },
    { href: '#superficies', claveTexto: 'admin.catalogoEstilo.superficies.titulo' },
    { href: '#datos', claveTexto: 'admin.catalogoEstilo.datos.titulo' },
    { href: '#tablas', claveTexto: 'admin.catalogoEstilo.tablas.titulo' },
    { href: '#fondo', claveTexto: 'admin.catalogoEstilo.fondo.titulo' },
    { href: '#temas', claveTexto: 'admin.catalogoEstilo.temas.titulo' },
  ];
}
