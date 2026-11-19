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
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import type { Idioma } from '../../core/i18n/idioma';
import {
  type EditorDeTraducciones as Editor,
  type TextoTraducible,
  type TipoTraducible,
  TraduccionesService,
} from '../../core/traducciones/traducciones.service';
import { Alert } from './alert';
import { Button } from './button';
import { Chip, type ChipTone } from './chip';

const PREFIJO_OPCION = 'option:';

const clave = (texto: Pick<TextoTraducible, 'entity_type' | 'entity_id' | 'field'>): string =>
  `${texto.entity_type}|${texto.entity_id}|${texto.field}`;

/**
 * Los textos traducibles de una entidad en un idioma: el original al lado,
 * la traducción editable, su estado y «Marcar como revisada».
 */
@Component({
  selector: 'app-editor-de-traducciones',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Chip],
  template: `
    <ng-container *transloco="let t; prefix: 'traducciones'">
      @if (error()) {
        <app-alert tone="error">{{ error() }}</app-alert>
      }
      @if (editor(); as e) {
        @if (e.items.length === 0) {
          <p class="vacio">{{ t('sinTextos') }}</p>
        } @else {
          <ul class="textos">
            @for (texto of e.items; track clave(texto)) {
              <li class="texto">
                <div class="cabecera">
                  <span class="campo">{{ etiqueta(texto) }}</span>
                  <app-chip [tone]="tono(texto)">{{ t('estado.' + texto.status) }}</app-chip>
                  @if (texto.origin) {
                    <span class="origen">{{ t('origen.' + texto.origin) }}</span>
                  }
                </div>
                <p class="original">{{ texto.original }}</p>
                <label class="visually-hidden" [for]="'trad-' + $index">{{
                  etiqueta(texto)
                }}</label>
                <textarea
                  [id]="'trad-' + $index"
                  [rows]="texto.original.length > 120 ? 5 : 2"
                  [value]="borrador(texto)"
                  (input)="escribir(texto, $any($event.target).value)"
                ></textarea>
                @if ((texto.value && texto.status !== 'al_dia') || texto.origin === 'ia') {
                  <app-button
                    variant="terciario"
                    [compacto]="true"
                    [disabled]="guardando()"
                    (pulsado)="revisar(texto)"
                    >{{ t('marcarRevisada') }}</app-button
                  >
                }
              </li>
            }
          </ul>
          <app-button
            [disabled]="cambios().length === 0"
            [loading]="guardando()"
            (pulsado)="guardar()"
            >{{ t('guardar') }}</app-button
          >
        }
      } @else if (!error()) {
        <p>{{ t('cargando') }}</p>
      }
    </ng-container>
  `,
  styles: `
    .textos {
      list-style: none;
      margin: 0 0 var(--space-md);
      padding: 0;
      display: grid;
      gap: var(--space-md);
    }
    .texto {
      display: grid;
      gap: var(--space-xs);
    }
    .cabecera {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-xs);
    }
    .campo {
      font-weight: 600;
    }
    .origen,
    .vacio {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .original {
      margin: 0;
      padding: var(--space-xs) var(--space-sm);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      color: var(--muted);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    textarea {
      width: 100%;
      font: inherit;
      padding: var(--space-xs) var(--space-sm);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--surface);
      color: var(--fg);
    }
  `,
})
export class EditorDeTraducciones {
  readonly tipo = input.required<TipoTraducible>();
  readonly entityId = input.required<string>();
  readonly locale = input.required<Idioma>();
  /** Nombre visible de cada campo (`title` → «Título»). */
  readonly etiquetas = input<Readonly<Record<string, string>>>({});

  private readonly servicio = inject(TraduccionesService);
  private readonly transloco = inject(TranslocoService);

  protected readonly editor = signal<Editor | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly guardando = signal(false);
  private readonly borradores = signal<Readonly<Record<string, string>>>({});
  protected readonly clave = clave;

  protected readonly cambios = computed(() => {
    const e = this.editor();
    const borradores = this.borradores();
    if (!e) {
      return [];
    }
    return e.items
      .filter((texto) => {
        const nuevo = borradores[clave(texto)];
        return nuevo !== undefined && nuevo !== (texto.value ?? '');
      })
      .map((texto) => ({
        entity_type: texto.entity_type,
        entity_id: texto.entity_id,
        field: texto.field,
        value: borradores[clave(texto)],
      }));
  });

  constructor() {
    effect(() => {
      const [tipo, id, locale] = [this.tipo(), this.entityId(), this.locale()];
      untracked(() => void this.cargar(() => this.servicio.obtener(tipo, id, locale)));
    });
  }

  protected etiqueta(texto: TextoTraducible): string {
    if (texto.entity_type === 'tag') {
      return `#${texto.field}`;
    }
    if (texto.field.startsWith(PREFIJO_OPCION)) {
      return this.transloco.translate('traducciones.opcion', {
        valor: texto.field.slice(PREFIJO_OPCION.length),
      });
    }
    const propia = this.etiquetas()[texto.field];
    if (propia) {
      return propia;
    }
    const comun = `traducciones.campos.${texto.field}`;
    const traducida = this.transloco.translate(comun);
    return traducida === comun ? texto.field : traducida;
  }

  protected tono(texto: TextoTraducible): ChipTone {
    return texto.status === 'al_dia'
      ? 'ok'
      : texto.status === 'desactualizada'
        ? 'espera'
        : 'apagado';
  }

  protected borrador(texto: TextoTraducible): string {
    return this.borradores()[clave(texto)] ?? texto.value ?? '';
  }

  protected escribir(texto: TextoTraducible, valor: string): void {
    this.borradores.update((actual) => ({ ...actual, [clave(texto)]: valor }));
  }

  protected guardar(): void {
    const cambios = this.cambios();
    void this.cargar(() =>
      this.servicio.guardar(this.tipo(), this.entityId(), this.locale(), cambios),
    );
  }

  protected revisar(texto: TextoTraducible): void {
    void this.cargar(() =>
      this.servicio.revisar(this.tipo(), this.entityId(), this.locale(), texto),
    );
  }

  private async cargar(peticion: () => Promise<Editor>): Promise<void> {
    this.guardando.set(true);
    this.error.set(null);
    try {
      this.editor.set(await peticion());
      this.borradores.set({});
    } catch {
      this.error.set(this.transloco.translate('traducciones.error'));
    } finally {
      this.guardando.set(false);
    }
  }
}
