import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { SegmentedFilter } from '../../../shared/ui/segmented-filter';
import { BotonesSection } from './sections/botones-section';
import { CamposSection } from './sections/campos-section';
import { ChipsSection } from './sections/chips-section';
import { ColorSection } from './sections/color-section';
import { DatosSection } from './sections/datos-section';
import { EstadosSection } from './sections/estados-section';
import { FondoSection } from './sections/fondo-section';
import { SelectSection } from './sections/select-section';
import { SuperficiesSection } from './sections/superficies-section';
import { CookiesSection } from './sections/cookies-section';
import { PatronesPanelSection } from './sections/patrones-panel-section';
import { TablasSection } from './sections/tablas-section';
import { TemasSection } from './sections/temas-section';
import { TipografiaSection } from './sections/tipografia-section';

/** Identificador de categoría del catálogo; cada una corresponde a una sección. */
export type Categoria =
  | 'color'
  | 'tipografia'
  | 'botones'
  | 'estados'
  | 'chips'
  | 'campos'
  | 'select'
  | 'superficies'
  | 'datos'
  | 'tablas'
  | 'patrones-panel'
  | 'fondo'
  | 'temas'
  | 'cookies';

/**
 * Réplica del prototipo real `sistema-componentes.html`: el catálogo interno de
 * `shared/ui`, sección por sección y en el mismo orden — pero en **pestañas
 * horizontales** por categoría (patrón del catálogo de Bloom Marbella), no en una
 * página larga con índice ancla: los enlaces ancla no llevaban a ningún sitio (las
 * secciones nunca tuvieron `id`) y una página de esta longitud era inabarcable.
 * Cada pestaña muestra su única sección; el resto no se monta.
 *
 * Cada sección vive en su propio componente bajo `./sections/` para mantener este
 * fichero corto y cada pieza enfocada en un único bloque del prototipo.
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
    SegmentedFilter,
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
    PatronesPanelSection,
    FondoSection,
    CookiesSection,
    TemasSection,
  ],
  template: `
    <ng-container *transloco="let t">
      <div class="cabecera-pagina">
        <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.titulo') }}</span>
        <h1>{{ t('admin.catalogoEstilo.encabezado') }}</h1>
        <p class="introduccion">{{ t('admin.catalogoEstilo.introduccion') }}</p>
      </div>

      <app-segmented-filter
        class="pestanas"
        [opciones]="pestanas()"
        [valor]="categoria()"
        [etiqueta]="t('admin.catalogoEstilo.indice')"
        (cambio)="categoria.set($event)"
      />

      @switch (categoria()) {
        @case ('color') {
          <app-style-guide-color-section />
        }
        @case ('tipografia') {
          <app-style-guide-tipografia-section />
        }
        @case ('botones') {
          <app-style-guide-botones-section />
        }
        @case ('estados') {
          <app-style-guide-estados-section />
        }
        @case ('chips') {
          <app-style-guide-chips-section />
        }
        @case ('campos') {
          <app-style-guide-campos-section />
        }
        @case ('select') {
          <app-style-guide-select-section />
        }
        @case ('superficies') {
          <app-style-guide-superficies-section />
        }
        @case ('datos') {
          <app-style-guide-datos-section />
        }
        @case ('tablas') {
          <app-style-guide-tablas-section />
        }
        @case ('patrones-panel') {
          <app-style-guide-patrones-panel-section />
        }
        @case ('fondo') {
          <app-style-guide-fondo-section />
        }
        @case ('temas') {
          <app-style-guide-temas-section />
        }
        @case ('cookies') {
          <app-style-guide-cookies-section />
        }
      }
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
    .pestanas {
      display: block;
      margin-bottom: var(--space-lg);
    }
  `,
})
export class StyleGuidePage {
  private readonly transloco = inject(TranslocoService);

  /** La pestaña activa; el orden de `CATEGORIAS` es el del prototipo. */
  protected readonly categoria = signal<Categoria>('color');

  protected readonly pestanas = computed<readonly { valor: Categoria; etiqueta: string }[]>(() =>
    CATEGORIAS.map((valor) => ({
      valor,
      etiqueta: this.transloco.translate('admin.catalogoEstilo.' + claveDe(valor) + '.titulo'),
    })),
  );
}

/** Orden de las pestañas, el mismo que tenían las secciones (y el del prototipo). */
export const CATEGORIAS: readonly Categoria[] = [
  'color',
  'tipografia',
  'botones',
  'estados',
  'chips',
  'campos',
  'select',
  'superficies',
  'datos',
  'tablas',
  'patrones-panel',
  'fondo',
  'temas',
  'cookies',
];

function claveDe(categoria: Categoria): string {
  return categoria === 'patrones-panel' ? 'patronesPanel' : categoria;
}
