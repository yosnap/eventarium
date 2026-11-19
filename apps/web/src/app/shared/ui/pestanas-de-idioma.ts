import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { NOMBRE_DEL_IDIOMA, type Idioma } from '../../core/i18n/idioma';
import {
  type EditorDeTraducciones as Editor,
  type TipoTraducible,
  TraduccionesService,
} from '../../core/traducciones/traducciones.service';
import { ThemingService } from '../../core/theming/theming.service';
import { AvisoClavePropia } from './aviso-clave-propia';
import { EditorDeTraducciones } from './editor-de-traducciones';

let siguienteId = 0;

/**
 * Pestañas de idioma de un formulario del panel. La del idioma original muestra
 * el formulario de siempre (el contenido proyectado, que sigue en el DOM para no
 * perder lo que se esté escribiendo); las demás, el editor de traducciones, que
 * tampoco se destruye al cambiar de pestaña.
 *
 * Sin entidad guardada todavía, o si la plataforma o la organización publican en
 * un solo idioma, no se muestran pestañas (ni se pregunta a la API) y el
 * formulario se ve siempre.
 */
@Component({
  selector: 'app-pestanas-de-idioma',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AvisoClavePropia, EditorDeTraducciones],
  template: `
    <ng-container *transloco="let t; prefix: 'traducciones'">
      @if (sinClavePropia()) {
        <app-aviso-clave-propia />
      }
      @if (pestanas().length > 1) {
        <div class="pestanas" role="tablist" [attr.aria-label]="t('pestanas')">
          @for (idioma of pestanas(); track idioma) {
            <button
              type="button"
              role="tab"
              [id]="id + '-tab-' + idioma"
              [attr.aria-controls]="id + '-panel-' + idioma"
              [attr.aria-selected]="idioma === activa()"
              [attr.tabindex]="idioma === activa() ? 0 : -1"
              [class.activa]="idioma === activa()"
              (click)="elegir(idioma)"
              (keydown)="teclado($event, idioma)"
            >
              {{ nombre(idioma) }}
              @if (idioma === origen()) {
                <span class="nota">({{ t('original') }})</span>
              }
            </button>
          }
        </div>
      }
      <div
        [id]="id + '-panel-' + origen()"
        [attr.role]="pestanas().length > 1 ? 'tabpanel' : null"
        [attr.aria-labelledby]="pestanas().length > 1 ? id + '-tab-' + origen() : null"
        [hidden]="activa() !== origen()"
      >
        <ng-content />
      </div>
      @if (entityId(); as entidad) {
        @for (idioma of visitadas(); track idioma) {
          <div
            role="tabpanel"
            [id]="id + '-panel-' + idioma"
            [attr.aria-labelledby]="id + '-tab-' + idioma"
            [hidden]="activa() !== idioma"
          >
            <app-editor-de-traducciones
              [tipo]="tipo()"
              [entityId]="entidad"
              [locale]="idioma"
              [etiquetas]="etiquetas()"
            />
          </div>
        }
      }
    </ng-container>
  `,
  styles: `
    .pestanas {
      margin-top: var(--space-md);
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs);
      margin-bottom: var(--space-md);
      border-bottom: 1px solid var(--border);
    }
    button {
      font: inherit;
      padding: var(--space-xs) var(--space-sm);
      border: 1px solid transparent;
      border-bottom: none;
      border-radius: var(--radius-sm) var(--radius-sm) 0 0;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
    }
    button.activa {
      border-color: var(--border);
      background: var(--surface);
      color: var(--fg);
      font-weight: 600;
    }
    .nota {
      font-weight: 400;
      color: var(--muted);
    }
  `,
})
export class PestanasDeIdioma {
  readonly tipo = input.required<TipoTraducible>();
  /** `null` mientras la entidad no existe (alta): no hay nada que traducir. */
  readonly entityId = input<string | null>(null);
  readonly etiquetas = input<Readonly<Record<string, string>>>({});

  protected readonly id = `pestanas-idioma-${siguienteId++}`;
  private readonly servicio = inject(TraduccionesService);
  private readonly theming = inject(ThemingService);
  /** La plataforma ofrece más de un idioma: si no, no hay nada que traducir. */
  private readonly variosIdiomas = computed(
    () => (this.theming.plataforma()?.enabled_locales?.length ?? 0) > 1,
  );
  private readonly info = signal<Pick<
    Editor,
    'locales' | 'source_locale' | 'auto_translation_available'
  > | null>(null);
  /** Varios idiomas y sin clave propia: hay que avisar de que no se traducirá solo. */
  protected readonly sinClavePropia = computed(
    () => this.pestanas().length > 1 && this.info()?.auto_translation_available === false,
  );
  /** Pestaña elegida; `null` es la del original (también tras cambiar de entidad). */
  private readonly elegida = signal<Idioma | null>(null);
  /** Idiomas cuyo editor ya se ha abierto: se conservan para no perder borradores. */
  protected readonly visitadas = signal<readonly Idioma[]>([]);

  protected readonly origen = computed<Idioma | null>(() => this.info()?.source_locale ?? null);
  protected readonly pestanas = computed<readonly Idioma[]>(() => {
    const info = this.info();
    if (!info) {
      return [];
    }
    return [info.source_locale, ...info.locales.filter((idioma) => idioma !== info.source_locale)];
  });
  protected readonly activa = computed(() => {
    const elegida = this.elegida();
    return elegida && this.pestanas().includes(elegida) ? elegida : this.origen();
  });

  constructor() {
    effect(() => {
      const [tipo, id, varios] = [this.tipo(), this.entityId(), this.variosIdiomas()];
      untracked(() => void this.conocerIdiomas(tipo, varios ? id : null));
    });
  }

  protected nombre(idioma: Idioma): string {
    return NOMBRE_DEL_IDIOMA[idioma];
  }

  protected elegir(idioma: Idioma): void {
    this.elegida.set(idioma === this.origen() ? null : idioma);
    if (idioma !== this.origen() && !this.visitadas().includes(idioma)) {
      this.visitadas.update((visitadas) => [...visitadas, idioma]);
    }
  }

  /** Flechas, Inicio y Fin mueven entre pestañas (patrón ARIA de pestañas). */
  protected teclado(evento: KeyboardEvent, actual: Idioma): void {
    const pestanas = this.pestanas();
    const indice = pestanas.indexOf(actual);
    const destino =
      evento.key === 'ArrowRight'
        ? pestanas[(indice + 1) % pestanas.length]
        : evento.key === 'ArrowLeft'
          ? pestanas[(indice - 1 + pestanas.length) % pestanas.length]
          : evento.key === 'Home'
            ? pestanas[0]
            : evento.key === 'End'
              ? pestanas[pestanas.length - 1]
              : undefined;
    if (!destino) {
      return;
    }
    evento.preventDefault();
    this.elegir(destino);
    document.getElementById(`${this.id}-tab-${destino}`)?.focus();
  }

  private async conocerIdiomas(tipo: TipoTraducible, id: string | null): Promise<void> {
    // Otra entidad (o un alta): se vuelve al formulario original y se descartan
    // los editores de la anterior.
    this.info.set(null);
    this.elegida.set(null);
    this.visitadas.set([]);
    if (!id) {
      return;
    }
    try {
      // Cualquier idioma sirve para saber los de la organización y el original.
      const editor = await this.servicio.obtener(tipo, id, 'en-US');
      if (this.entityId() === id) {
        this.info.set({
          locales: editor.locales,
          source_locale: editor.source_locale,
          auto_translation_available: editor.auto_translation_available,
        });
      }
    } catch {
      // Sin permiso de lectura o sin conexión: el formulario sigue funcionando.
      this.info.set(null);
    }
  }
}
