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

import { IDIOMAS, NOMBRE_DEL_IDIOMA, type Idioma } from '../../core/i18n/idioma';
import {
  type EditorDeTraducciones as Editor,
  type TipoTraducible,
  TraduccionesService,
} from '../../core/traducciones/traducciones.service';
import { ThemingService } from '../../core/theming/theming.service';
import { EditorDeTraducciones } from './editor-de-traducciones';

/**
 * Pestañas de idioma de un formulario del panel. La del idioma original muestra
 * el formulario de siempre (el contenido proyectado, que sigue en el DOM para no
 * perder lo que se esté escribiendo); las demás, el editor de traducciones.
 * Sin entidad guardada todavía, o si la plataforma o la organización publican en
 * un solo idioma, no se muestran pestañas (ni se pregunta a la API).
 */
@Component({
  selector: 'app-pestanas-de-idioma',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, EditorDeTraducciones],
  template: `
    <ng-container *transloco="let t; prefix: 'traducciones'">
      @if (pestanas().length > 1) {
        <div class="pestanas" role="tablist" [attr.aria-label]="t('pestanas')">
          @for (idioma of pestanas(); track idioma) {
            <button
              type="button"
              role="tab"
              [attr.aria-selected]="idioma === activa()"
              [class.activa]="idioma === activa()"
              (click)="activa.set(idioma)"
            >
              {{ nombre(idioma) }}
              @if (idioma === origen()) {
                <span class="nota">({{ t('original') }})</span>
              }
            </button>
          }
        </div>
      }
      <div [hidden]="activa() !== origen()">
        <ng-content />
      </div>
      @if (activa() !== origen() && entityId(); as id) {
        <app-editor-de-traducciones
          [tipo]="tipo()"
          [entityId]="id"
          [locale]="activa()"
          [etiquetas]="etiquetas()"
        />
      }
    </ng-container>
  `,
  styles: `
    .pestanas {
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

  private readonly servicio = inject(TraduccionesService);
  private readonly theming = inject(ThemingService);
  /** La plataforma ofrece más de un idioma: si no, no hay nada que traducir. */
  private readonly variosIdiomas = computed(
    () => (this.theming.plataforma()?.enabled_locales?.length ?? 0) > 1,
  );
  private readonly info = signal<Pick<Editor, 'locales' | 'source_locale'> | null>(null);

  protected readonly origen = computed<Idioma>(() => this.info()?.source_locale ?? IDIOMAS[0]);
  protected readonly pestanas = computed<readonly Idioma[]>(() => {
    const info = this.info();
    if (!info) {
      return [];
    }
    return [info.source_locale, ...info.locales.filter((idioma) => idioma !== info.source_locale)];
  });
  protected readonly activa = signal<Idioma>(IDIOMAS[0]);

  constructor() {
    effect(() => {
      const [tipo, id, varios] = [this.tipo(), this.entityId(), this.variosIdiomas()];
      untracked(() => void this.conocerIdiomas(tipo, varios ? id : null));
    });
  }

  protected nombre(idioma: Idioma): string {
    return NOMBRE_DEL_IDIOMA[idioma];
  }

  private async conocerIdiomas(tipo: TipoTraducible, id: string | null): Promise<void> {
    this.info.set(null);
    if (!id) {
      return;
    }
    try {
      // Cualquier idioma sirve para saber los de la organización y el original.
      const editor = await this.servicio.obtener(tipo, id, IDIOMAS[IDIOMAS.length - 1]);
      this.info.set({ locales: editor.locales, source_locale: editor.source_locale });
      this.activa.set(editor.source_locale);
    } catch {
      // Sin permiso de lectura o sin conexión: el formulario sigue funcionando.
      this.info.set(null);
    }
  }
}
