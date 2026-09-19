import { HttpClient, HttpParams } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import { ApiError } from '../../core/api/error.interceptor';
import { Button } from './button';
import { Input } from './input';
import { MediaCropEditor, RectanguloDeRecorte } from './media-crop-editor';

/** Catálogo cerrado — igual que `KIND_A_PERMISO` en el backend
 * (`app/modules/media/service.py`). `platform` no lleva `kind` en sus
 * peticiones: es un único contexto sin ese campo. */
export type MediaKind = 'branding' | 'events' | 'sponsors' | 'platform';

/** Lo que produce elegir una imagen por cualquiera de las 3 vías (fichero,
 * URL, biblioteca): un medio ya persistido, nunca un `File` ni una URL
 * suelta — el consumidor llama a SU propio endpoint de asignación con este
 * `id` (contrato `{media_id}` de la Fase 2). */
export interface MediaElegida {
  readonly id: string;
  readonly url: string;
}

interface MediaItem {
  readonly id: string;
  readonly url: string;
  readonly filename: string;
  readonly alt: string | null;
}

interface MediaFolder {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
}

interface MediaPage {
  readonly items: readonly MediaItem[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
}

const LIMITE = 12;
const RETARDO_BUSQUEDA_MS = 300;

function baseDeMedia(kind: MediaKind): string {
  return kind === 'platform' ? '/admin/platform/media' : '/organizations/me/media';
}

function baseDeCarpetas(kind: MediaKind): string {
  return kind === 'platform' ? '/admin/platform/media-folders' : '/organizations/me/media-folders';
}

/**
 * Contenido de selección de medios: pestañas Subir (dropzone + selector de
 * fichero), URL (importar por dirección) y Biblioteca (rejilla paginada
 * contra `GET .../media`, con buscador y filtro de carpeta).
 *
 * Contrato de la Fase 3 del plan `260918-1944-biblioteca-de-medios`: las 3
 * vías terminan siempre en un `media_id` real (el propio componente hace la
 * subida/asignación contra el backend) — antes emitía un `File` o una URL
 * suelta y dejaba la persistencia a quien lo envolviera, lo que dejaba
 * "elegir de biblioteca" sin ningún efecto real (hallazgo de red-team 4).
 *
 * Sin envoltorio de modal a propósito: `MediaDialog` lo mete dentro de
 * `app-dialog` para el caso "cambiar" (ya hay imagen, no se quiere ocupar el
 * espacio del campo con el dropzone entero); `MediaPicker` lo usa directo,
 * sin modal, mientras el campo no tenga imagen.
 */
@Component({
  selector: 'app-media-fields',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, Input, MediaCropEditor],
  template: `
    <ng-container *transloco="let t">
      @if (pestanasDisponibles().length > 1) {
        <div class="pestanas" role="tablist">
          @for (tab of pestanasDisponibles(); track tab.valor) {
            <button
              type="button"
              role="tab"
              [class.pestana-activa]="pestana() === tab.valor"
              [attr.aria-selected]="pestana() === tab.valor"
              (click)="cambiarPestana(tab.valor)"
            >
              {{ t(tab.etiqueta) }}
            </button>
          }
        </div>
      }

      @if (error(); as mensaje) {
        <p class="error">{{ mensaje }}</p>
      }

      @switch (pestana()) {
        @case ('subir') {
          <label
            class="dropzone"
            [class.encima]="arrastrando()"
            [class.deshabilitado]="subiendo()"
            (dragover)="alArrastrarEncima($event)"
            (dragleave)="arrastrando.set(false)"
            (drop)="alSoltar($event)"
          >
            <input
              type="file"
              class="fichero-oculto"
              [accept]="aceptados()"
              [disabled]="subiendo()"
              (change)="alElegirFichero($event)"
            />
            @if (subiendo()) {
              <span>{{ t('comun.cargando') }}</span>
            } @else {
              <span>{{ t('ui.media.sueltaAqui') }}</span>
              <small>{{ t('ui.media.oPulsaParaElegir') }}</small>
            }
          </label>
        }
        @case ('url') {
          <app-input
            [fieldId]="idUrl"
            [label]="t('ui.media.urlEtiqueta')"
            [value]="urlEscrita()"
            [disabled]="subiendo()"
            (valueChange)="urlEscrita.set($event)"
          />
          <app-button
            type="button"
            variant="secundario"
            [disabled]="!urlEscrita().trim() || subiendo()"
            [loading]="subiendo()"
            (pulsado)="elegirUrl()"
          >
            {{ subiendo() ? t('ui.media.subiendoUrl') : t('ui.media.usarUrl') }}
          </app-button>
        }
        @case ('biblioteca') {
          @if (recortando(); as item) {
            <app-media-crop-editor
              [url]="item.url"
              [confirmando]="recortandoEnCurso()"
              (confirmado)="confirmarRecorte($event)"
              (cancelado)="recortando.set(null)"
            />
          } @else {
            <div class="biblioteca-controles">
              <app-input
                [fieldId]="idBuscar"
                [label]="t('ui.media.buscarEtiqueta')"
                [etiquetaOculta]="true"
                [value]="buscar()"
                (valueChange)="alBuscar($event)"
              />
              @if (carpetas().length > 0) {
                <label class="carpeta-filtro">
                  {{ t('ui.media.carpetaEtiqueta') }}
                  <select (change)="alFiltrarCarpeta($event)">
                    <option value="">{{ t('ui.media.todasLasCarpetas') }}</option>
                    @for (carpeta of carpetas(); track carpeta.id) {
                      <option [value]="carpeta.id">{{ carpeta.name }}</option>
                    }
                  </select>
                </label>
              }
            </div>

            @if (cargandoBiblioteca()) {
              <p>{{ t('comun.cargando') }}</p>
            } @else if (bibliotecaItems().length === 0) {
              <p class="vacio">
                {{ buscar() ? t('ui.media.sinResultados') : t('ui.media.bibliotecaVacia') }}
              </p>
            } @else {
              <div class="rejilla" role="group" [attr.aria-label]="etiqueta()">
                @for (item of bibliotecaItems(); track item.id) {
                  <div class="item-envoltorio">
                    <button
                      type="button"
                      class="item"
                      [attr.aria-label]="item.alt ?? item.filename"
                      (click)="elegirBiblioteca(item)"
                    >
                      <img [src]="item.url" alt="" loading="lazy" />
                    </button>
                    <div class="item-acciones">
                      <button type="button" class="accion-texto" (click)="abrirRecorte(item)">
                        {{ t('ui.media.recortar') }}
                      </button>
                      <button
                        type="button"
                        class="accion-texto accion-peligro"
                        [disabled]="borrandoId() === item.id"
                        (click)="enviarAPapelera(item)"
                      >
                        {{ t('ui.media.papelera') }}
                      </button>
                    </div>
                  </div>
                }
              </div>

              @if (totalPaginas() > 1) {
                <nav class="paginacion" [attr.aria-label]="etiqueta()">
                  <app-button
                    variant="secundario"
                    type="button"
                    [disabled]="bibliotecaOffset() === 0"
                    (pulsado)="irAPagina(bibliotecaOffset() - LIMITE)"
                  >
                    {{ t('ui.media.anterior') }}
                  </app-button>
                  <span>
                    {{ t('ui.media.paginaDe', { actual: paginaActual(), total: totalPaginas() }) }}
                  </span>
                  <app-button
                    variant="secundario"
                    type="button"
                    [disabled]="bibliotecaOffset() + LIMITE >= bibliotecaTotal()"
                    (pulsado)="irAPagina(bibliotecaOffset() + LIMITE)"
                  >
                    {{ t('ui.media.siguiente') }}
                  </app-button>
                </nav>
              }
            }
          }
        }
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .pestanas {
      display: flex;
      gap: var(--sp-1);
      border-bottom: 1px solid var(--border);
      margin-bottom: var(--sp-4);
    }
    [role='tab'] {
      padding: var(--sp-2) var(--sp-3);
      border: none;
      background: none;
      color: var(--muted);
      font: inherit;
      font-size: var(--fs-sm);
      cursor: pointer;
      border-bottom: 2px solid transparent;
    }
    .pestana-activa {
      color: var(--fg);
      border-bottom-color: var(--accent);
    }
    .dropzone {
      display: grid;
      place-items: center;
      gap: var(--space-xs);
      min-height: 8rem;
      padding: var(--sp-4);
      border: 2px dashed var(--border-strong);
      border-radius: var(--radius-md);
      cursor: pointer;
      text-align: center;
      color: var(--muted);
    }
    .dropzone.encima {
      border-color: var(--accent);
      color: var(--fg);
    }
    .dropzone.deshabilitado {
      cursor: wait;
      opacity: 0.7;
    }
    .fichero-oculto {
      display: none;
    }
    .vacio {
      color: var(--muted);
      margin: 0;
    }
    .error {
      color: var(--danger);
      font-size: var(--fs-sm);
      margin: 0 0 var(--space-sm);
    }
    .biblioteca-controles {
      display: flex;
      gap: var(--space-sm);
      align-items: flex-end;
      margin-bottom: var(--space-sm);
      flex-wrap: wrap;
    }
    .carpeta-filtro {
      display: grid;
      gap: var(--space-xs);
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .carpeta-filtro select {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      font: inherit;
      background: var(--surface);
      color: var(--fg);
    }
    .rejilla {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(6rem, 1fr));
      gap: var(--sp-2);
      max-height: 20rem;
      overflow: auto;
    }
    .item-envoltorio {
      display: grid;
      gap: 2px;
    }
    .item {
      padding: 0;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: none;
      cursor: pointer;
      overflow: hidden;
      aspect-ratio: 1;
    }
    .item img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .item-acciones {
      display: flex;
      justify-content: space-between;
      gap: 2px;
    }
    .accion-texto {
      flex: 1;
      border: none;
      background: none;
      color: var(--muted);
      font-size: 0.6875rem;
      cursor: pointer;
      padding: 2px;
    }
    .accion-texto:hover {
      color: var(--fg);
    }
    .accion-peligro:hover {
      color: var(--danger);
    }
    .paginacion {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      justify-content: center;
      margin-top: var(--space-sm);
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    app-button {
      margin-top: var(--space-sm);
    }
  `,
})
export class MediaFields {
  private static contador = 0;
  /** Id único por instancia: dos `MediaFields` en la misma página (p. ej.
   * logo y favicon en identidad de plataforma) no pueden compartir el id del
   * campo de URL — `label[for]` apuntaría al input equivocado (hallazgo de
   * red-team). */
  protected readonly idUrl = `media-url-${MediaFields.contador++}`;
  protected readonly idBuscar = `media-buscar-${MediaFields.contador++}`;
  protected readonly LIMITE = LIMITE;

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  constructor() {
    // Sin esto, cerrar el diálogo (o navegar) justo tras teclear en el
    // buscador deja el `setTimeout` vivo, y su callback dispara un `GET`
    // contra un componente ya destruido (hallazgo de code-review).
    inject(DestroyRef).onDestroy(() => this.limpiarTemporizadorDeBusqueda());
  }

  /** Tipos aceptados por el selector de fichero (igual que `accept`). */
  readonly aceptados = input.required<string>();
  /** A qué campo pertenece la imagen — resuelve el permiso requerido y el
   * endpoint de biblioteca contra el que trabajar (organización o
   * plataforma). */
  readonly kind = input.required<MediaKind>();
  /** Etiqueta accesible de la rejilla de biblioteca (título del campo/diálogo). */
  readonly etiqueta = input('');
  /** Si el consumidor puede elegir/subir por URL. */
  readonly permitirUrl = input(true);

  /** El medio ya persistido, por cualquiera de las 3 vías. */
  readonly mediaElegido = output<MediaElegida>();

  protected readonly pestana = signal<'subir' | 'url' | 'biblioteca'>('subir');
  protected readonly arrastrando = signal(false);
  protected readonly urlEscrita = signal('');
  protected readonly subiendo = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly bibliotecaItems = signal<readonly MediaItem[]>([]);
  protected readonly bibliotecaTotal = signal(0);
  protected readonly bibliotecaOffset = signal(0);
  protected readonly cargandoBiblioteca = signal(false);
  protected readonly buscar = signal('');
  protected readonly carpetas = signal<readonly MediaFolder[]>([]);
  protected readonly carpetaFiltro = signal<string | null>(null);
  private bibliotecaCargada = false;
  private temporizadorBusqueda: ReturnType<typeof setTimeout> | null = null;

  protected readonly recortando = signal<MediaItem | null>(null);
  protected readonly recortandoEnCurso = signal(false);
  protected readonly borrandoId = signal<string | null>(null);

  protected readonly totalPaginas = computed(() =>
    Math.max(1, Math.ceil(this.bibliotecaTotal() / LIMITE)),
  );
  protected readonly paginaActual = computed(
    () => Math.floor(this.bibliotecaOffset() / LIMITE) + 1,
  );

  protected readonly pestanasDisponibles = computed(() =>
    (
      [
        { valor: 'subir' as const, etiqueta: 'ui.media.pestanaSubir' },
        { valor: 'url' as const, etiqueta: 'ui.media.pestanaUrl' },
        { valor: 'biblioteca' as const, etiqueta: 'ui.media.pestanaBiblioteca' },
      ] as const
    ).filter((tab) => (tab.valor === 'url' ? this.permitirUrl() : true)),
  );

  /** Reinicia a la pestaña Subir y recarga la biblioteca de cero — quien
   * envuelve este componente en un diálogo lo llama al reabrirlo, para no
   * arrastrar el estado (ni datos ya obsoletos) de la vez anterior. */
  reiniciar(): void {
    this.pestana.set('subir');
    this.urlEscrita.set('');
    this.error.set(null);
    this.recortando.set(null);
    this.bibliotecaCargada = false;
    this.limpiarTemporizadorDeBusqueda();
  }

  private limpiarTemporizadorDeBusqueda(): void {
    if (this.temporizadorBusqueda) {
      clearTimeout(this.temporizadorBusqueda);
      this.temporizadorBusqueda = null;
    }
  }

  protected cambiarPestana(valor: 'subir' | 'url' | 'biblioteca'): void {
    this.pestana.set(valor);
    this.error.set(null);
    if (valor === 'biblioteca' && !this.bibliotecaCargada) {
      this.bibliotecaCargada = true;
      void this.cargarCarpetas();
      void this.cargarBiblioteca();
    }
  }

  protected alArrastrarEncima(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(true);
  }

  protected alElegirFichero(evento: Event): void {
    const fichero = (evento.target as HTMLInputElement).files?.[0];
    if (fichero) {
      void this.subirFichero(fichero);
    }
  }

  protected alSoltar(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(false);
    const fichero = evento.dataTransfer?.files?.[0];
    if (fichero) {
      void this.subirFichero(fichero);
    }
  }

  private async subirFichero(fichero: File): Promise<void> {
    this.subiendo.set(true);
    this.error.set(null);
    try {
      const datos = new FormData();
      datos.append('fichero', fichero);
      if (this.kind() !== 'platform') {
        datos.append('kind', this.kind());
      }
      const nuevo = await firstValueFrom(
        this.http.post<MediaItem>(this.api.url(baseDeMedia(this.kind())), datos),
      );
      this.mediaElegido.emit({ id: nuevo.id, url: nuevo.url });
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.subiendo.set(false);
    }
  }

  protected async elegirUrl(): Promise<void> {
    const url = this.urlEscrita().trim();
    if (!url || this.subiendo()) {
      return;
    }
    this.subiendo.set(true);
    this.error.set(null);
    try {
      const cuerpo: Record<string, string> = { url };
      if (this.kind() !== 'platform') {
        cuerpo['kind'] = this.kind();
      }
      const nuevo = await firstValueFrom(
        this.http.post<MediaItem>(this.api.url(baseDeMedia(this.kind())), cuerpo),
      );
      this.urlEscrita.set('');
      this.mediaElegido.emit({ id: nuevo.id, url: nuevo.url });
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.subiendo.set(false);
    }
  }

  protected elegirBiblioteca(item: MediaItem): void {
    this.mediaElegido.emit({ id: item.id, url: item.url });
  }

  private async cargarCarpetas(): Promise<void> {
    try {
      const carpetas = await firstValueFrom(
        this.http.get<MediaFolder[]>(this.api.url(baseDeCarpetas(this.kind()))),
      );
      this.carpetas.set(carpetas);
    } catch {
      // Sin carpetas que ofrecer, el filtro simplemente no aparece — no es un
      // error que deba tapar la biblioteca entera.
      this.carpetas.set([]);
    }
  }

  private async cargarBiblioteca(): Promise<void> {
    this.cargandoBiblioteca.set(true);
    this.error.set(null);
    try {
      let params = new HttpParams().set('limit', LIMITE).set('offset', this.bibliotecaOffset());
      if (this.kind() !== 'platform') {
        params = params.set('kind', this.kind());
      }
      if (this.buscar().trim()) {
        params = params.set('search', this.buscar().trim());
      }
      if (this.carpetaFiltro()) {
        params = params.set('folder_id', this.carpetaFiltro()!);
      }
      const pagina = await firstValueFrom(
        this.http.get<MediaPage>(this.api.url(baseDeMedia(this.kind())), { params }),
      );
      this.bibliotecaItems.set(pagina.items);
      this.bibliotecaTotal.set(pagina.total);
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.cargandoBiblioteca.set(false);
    }
  }

  protected alBuscar(valor: string): void {
    this.buscar.set(valor);
    this.limpiarTemporizadorDeBusqueda();
    this.temporizadorBusqueda = setTimeout(() => {
      this.bibliotecaOffset.set(0);
      void this.cargarBiblioteca();
    }, RETARDO_BUSQUEDA_MS);
  }

  protected alFiltrarCarpeta(evento: Event): void {
    const valor = (evento.target as HTMLSelectElement).value;
    this.carpetaFiltro.set(valor || null);
    this.bibliotecaOffset.set(0);
    void this.cargarBiblioteca();
  }

  protected irAPagina(offset: number): void {
    this.bibliotecaOffset.set(offset);
    void this.cargarBiblioteca();
  }

  protected abrirRecorte(item: MediaItem): void {
    this.recortando.set(item);
  }

  protected async confirmarRecorte(rectangulo: RectanguloDeRecorte): Promise<void> {
    const item = this.recortando();
    if (!item) {
      return;
    }
    this.recortandoEnCurso.set(true);
    try {
      const nuevo = await firstValueFrom(
        this.http.patch<MediaItem>(
          this.api.url(`${baseDeMedia(this.kind())}/${item.id}/crop`),
          rectangulo,
        ),
      );
      this.recortando.set(null);
      // El recorte se ofrece directamente como si se hubiera elegido de
      // biblioteca (Requirements de la Fase 3): sin este paso, confirmar un
      // recorte no tendría ningún efecto visible hasta volver a buscarlo a
      // mano en la rejilla.
      this.mediaElegido.emit({ id: nuevo.id, url: nuevo.url });
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.recortandoEnCurso.set(false);
    }
  }

  protected async enviarAPapelera(item: MediaItem): Promise<void> {
    // Confirmación + bloqueo de doble clic — la clave de confirmación
    // existía en el catálogo de traducciones desde el principio pero nunca
    // se cableó, y sin un estado "en curso" un doble clic dispara dos
    // `DELETE` (hallazgo de code-review).
    const confirmacion = this.transloco.translate('ui.media.papeleraConfirmacion');
    if (this.borrandoId() || !window.confirm(confirmacion)) {
      return;
    }
    this.borrandoId.set(item.id);
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.delete<void>(this.api.url(`${baseDeMedia(this.kind())}/${item.id}`)),
      );
      await this.cargarBiblioteca();
    } catch (error) {
      this.error.set(this.mensajeDePapeleraEnUso(error));
    } finally {
      this.borrandoId.set(null);
    }
  }

  private mensajeDePapeleraEnUso(error: unknown): string {
    if (error instanceof ApiError && error.status === 409) {
      const usados = error.problem?.['used_by'];
      if (Array.isArray(usados) && usados.length > 0) {
        const nombres = usados
          .map((u: Record<string, unknown>) =>
            typeof u['nombre'] === 'string' ? u['nombre'] : u['tipo'],
          )
          .join(', ');
        return this.transloco.translate('ui.media.enUso', { recursos: nombres });
      }
    }
    return this.mensajeDeError(error);
  }

  private mensajeDeError(error: unknown): string {
    return error instanceof ApiError ? error.message : this.transloco.translate('comun.error');
  }
}
