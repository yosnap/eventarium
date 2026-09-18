import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  signal,
  type OnInit,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import {
  colorTieneCromaSuficiente,
  derivarPaletaDeAcento,
} from '../../../core/theming/accent-palette';
import {
  FAMILIAS_BODY,
  FAMILIAS_DISPLAY,
  PlantillaDeTema,
} from '../../../core/theming/theme-template.model';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { PageHeader } from '../../../shared/ui/page-header';
import { Select, type SelectOption } from '../../../shared/ui/select';
import { ThemeTemplatePreview } from '../superadmin/theme-template-preview';

/** Solo los campos que esta pantalla necesita del evento — mismo patrón que
 * `EventoBase` en `event-form.ts`, no un tipo global compartido. */
interface EventoDiseno {
  readonly id: string;
  readonly theme_template_id: string | null;
  readonly theme_overrides: {
    accent?: string;
    'font-display'?: string;
    'font-body'?: string;
  } | null;
}

interface BrandingDiseno {
  readonly theme_template_id: string | null;
}

/** Qué acción está en vuelo — una sola a la vez (cola de un elemento, ver
 * `enviarSiguiente`), para no dejar que dos PATCH concurrentes se pisen.
 * `combinada` existe para no perder una personalización ya en cola cuando
 * llega un cambio de plantilla (o viceversa) antes de que el PATCH en
 * vuelo responda: el backend acepta los dos campos en el mismo PATCH, así
 * que se funden en uno solo en vez de que el último en llegar descarte al
 * anterior (hallazgo del red-team de la fase 3). */
type AccionDePersonalizacion =
  | { readonly tipo: 'plantilla'; readonly plantillaId: string }
  | { readonly tipo: 'personalizar'; readonly overrides: EventoDiseno['theme_overrides'] }
  | {
      readonly tipo: 'combinada';
      readonly plantillaId: string;
      readonly overrides: EventoDiseno['theme_overrides'];
    };

/**
 * "Diseño" del evento: elegir plantilla base (aplica al clic) y
 * personalizarla con un color de acento y dos tipografías (aplican al
 * cambiar), todo sin botón "Guardar" — fiel al mockup aprobado
 * (https://claude.ai/artifact/7xrULG1SRh2WF83EJ1wHa8).
 *
 * La plantilla activa se resuelve en cliente con la misma cadena que ya usa
 * el backend (`_tema_del_evento`): evento → organización → catálogo. La
 * vista previa de los dos modos también se calcula en cliente
 * (`derivarPaletaDeAcento`), con la misma fórmula que el backend aplica de
 * verdad en la página pública — no hay un segundo resolutor de tokens en
 * el servidor para el organizador.
 */
@Component({
  selector: 'app-event-design',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Card, PageHeader, Select, ThemeTemplatePreview],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.events.design.titulo')">
        {{ t('admin.events.design.cabeceraInicio') }}
        <span class="mark">{{ t('admin.events.design.cabeceraMarca') }}</span>
      </app-page-header>

      <p class="descripcion">{{ t('admin.events.design.descripcion') }}</p>

      @if (mensajeAplicado(); as mensaje) {
        <p class="estado-auto" role="status">{{ mensaje }}</p>
      }
      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <app-card [heading]="t('admin.events.design.plantillaTitulo')">
          <p class="descripcion">{{ t('admin.events.design.plantillaDescripcion') }}</p>
          <div class="plantillas">
            @for (plantilla of plantillas(); track plantilla.id) {
              <button
                type="button"
                class="plantilla-tarjeta"
                [class.plantilla-activa]="plantilla.id === plantillaActivaId()"
                [attr.aria-pressed]="plantilla.id === plantillaActivaId()"
                [disabled]="accionEnCurso() !== null"
                (click)="elegirPlantilla(plantilla)"
              >
                <span class="plantilla-mini-marco">
                  <app-theme-template-preview
                    class="plantilla-miniatura"
                    [tokens]="plantilla.tokens"
                    [modo]="modoDeMiniatura(plantilla)"
                  />
                </span>
                <span class="pie-plantilla">
                  <span class="nombre">{{ plantilla.name }}</span>
                  @if (plantilla.id === plantillaActivaId()) {
                    <span class="insignia">{{ t('admin.events.design.aplicada') }}</span>
                  }
                </span>
              </button>
            }
          </div>
        </app-card>

        <app-card [heading]="t('admin.events.design.personalizarTitulo')">
          <p class="descripcion">{{ t('admin.events.design.personalizarDescripcion') }}</p>

          <div class="personalizar">
            <div class="campos">
              <div class="campo">
                <label for="event-design-color">{{ t('admin.events.design.colorAcento') }}</label>
                <div class="fila-color">
                  <input
                    id="event-design-color"
                    type="color"
                    [value]="colorAcento()"
                    [disabled]="accionEnCurso() !== null"
                    (input)="alCambiarColor($event)"
                  />
                  <input
                    type="text"
                    class="hex"
                    [attr.aria-label]="t('admin.events.design.colorAcento')"
                    [value]="colorAcento()"
                    [disabled]="accionEnCurso() !== null"
                    (change)="alCambiarColor($event)"
                  />
                </div>
              </div>

              <app-select
                fieldId="event-design-fuente-titulo"
                [label]="t('admin.events.design.fuenteTitulo')"
                [options]="opcionesFuenteDisplay"
                [value]="fuenteTitulo()"
                (valueChange)="alCambiarFuenteTitulo($event)"
              />

              <app-select
                fieldId="event-design-fuente-texto"
                [label]="t('admin.events.design.fuenteTexto')"
                [options]="opcionesFuenteTexto"
                [value]="fuenteTexto()"
                (valueChange)="alCambiarFuenteTexto($event)"
              />
            </div>

            <div class="previews">
              <div class="preview-modo">
                <p class="etiqueta">{{ t('admin.events.design.previewOscuro') }}</p>
                <app-theme-template-preview [tokens]="tokensDePreview()" modo="dark" />
              </div>
              <div class="preview-modo">
                <p class="etiqueta">{{ t('admin.events.design.previewClaro') }}</p>
                <app-theme-template-preview [tokens]="tokensDePreview()" modo="light" />
              </div>
            </div>
          </div>
        </app-card>
      }
    </ng-container>
  `,
  styles: `
    .descripcion {
      margin: 0 0 var(--space-md);
      color: var(--muted);
    }
    .estado-auto {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      font-family: var(--font-mono);
      font-size: var(--fs-sm);
      color: var(--accent);
      margin: 0 0 var(--space-md);
    }
    .plantillas {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
      gap: var(--sp-4);
    }
    .plantilla-tarjeta {
      display: grid;
      gap: var(--space-xs);
      padding: var(--sp-3);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: none;
      cursor: pointer;
      font: inherit;
      color: var(--fg);
      text-align: left;
    }
    .plantilla-tarjeta:hover:not(:disabled) {
      border-color: var(--border-strong);
    }
    .plantilla-tarjeta:disabled {
      cursor: not-allowed;
      opacity: 0.7;
    }
    .plantilla-activa {
      border-color: var(--accent);
      border-width: 2px;
      padding: calc(var(--sp-3) - 1px);
    }
    /* Mismo ajuste de escala que branding-page.ts: ThemeTemplatePreview está
       pensado para su tamaño real; se renderiza a un ancho de referencia y
       se reescala visualmente para no desbordar texto en un hueco pequeño. */
    .plantilla-mini-marco {
      --ancho-referencia: 13rem;
      --factor-escala: 0.95;
      overflow: hidden;
      border-radius: var(--radius-md);
      aspect-ratio: 4 / 3;
    }
    .plantilla-miniatura {
      display: block;
      width: var(--ancho-referencia);
      transform: scale(var(--factor-escala));
      transform-origin: top left;
      pointer-events: none;
    }
    .pie-plantilla {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-xs);
    }
    .nombre {
      font-weight: 500;
    }
    .insignia {
      font-family: var(--font-mono);
      font-size: var(--fs-label, 0.7rem);
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--on-accent);
      background: var(--accent);
      padding: 2px 8px;
      border-radius: 999px;
    }
    .personalizar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
      gap: var(--space-lg);
    }
    @media (max-width: 52rem) {
      .personalizar {
        grid-template-columns: 1fr;
      }
    }
    .campos {
      display: grid;
      gap: var(--space-md);
      align-content: start;
    }
    .campo label {
      display: block;
      font-size: var(--fs-sm);
      color: var(--muted);
      margin-bottom: var(--space-xs);
    }
    .fila-color {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    input[type='color'] {
      width: 44px;
      height: 40px;
      padding: 0;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: none;
      cursor: pointer;
    }
    input[type='text'].hex {
      font-family: var(--font-mono);
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      color: var(--fg);
      padding: 8px 10px;
      width: 8rem;
    }
    .previews {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-md);
    }
    @media (max-width: 30rem) {
      .previews {
        grid-template-columns: 1fr;
      }
    }
    .etiqueta {
      font-family: var(--font-mono);
      font-size: var(--fs-sm);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 var(--space-xs);
    }
  `,
})
export class EventDesign implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly plantillas = signal<readonly PlantillaDeTema[]>([]);
  protected readonly brandingThemeId = signal<string | null>(null);
  protected readonly evento = signal<EventoDiseno | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly mensajeAplicado = signal<string | null>(null);

  /** Cola de un elemento: la acción en vuelo, y como mucho una esperando
   * detrás. Vacía el debounce de color pendiente antes de encolar cualquier
   * otra cosa (ver `enviarSiguiente`). */
  protected readonly accionEnCurso = signal<AccionDePersonalizacion | null>(null);
  private accionPendiente: AccionDePersonalizacion | null = null;
  private temporizadorColor: ReturnType<typeof setTimeout> | null = null;
  private colorPendiente: string | null = null;

  protected readonly opcionesFuenteDisplay: readonly SelectOption[] = FAMILIAS_DISPLAY.map(
    (familia) => ({ value: familia, label: familia }),
  );
  protected readonly opcionesFuenteTexto: readonly SelectOption[] = FAMILIAS_BODY.map(
    (familia) => ({ value: familia, label: familia }),
  );

  protected readonly plantillaActivaId = computed(() => {
    const evento = this.evento();
    if (!evento) {
      return null;
    }
    return (
      evento.theme_template_id ??
      this.brandingThemeId() ??
      this.plantillas().find((p) => p.is_default)?.id ??
      null
    );
  });

  private readonly plantillaActiva = computed(() =>
    this.plantillas().find((p) => p.id === this.plantillaActivaId()),
  );

  protected readonly colorAcento = computed(() => {
    const guardado = this.evento()?.theme_overrides?.accent;
    return guardado ?? '#22c55e';
  });
  protected readonly fuenteTitulo = computed(() => {
    const guardada = this.evento()?.theme_overrides?.['font-display'];
    return guardada ?? this.opcionesFuenteDisplay[0]?.value ?? '';
  });
  protected readonly fuenteTexto = computed(() => {
    const guardada = this.evento()?.theme_overrides?.['font-body'];
    return guardada ?? this.opcionesFuenteTexto[0]?.value ?? '';
  });

  /** Tokens combinados (plantilla activa + overrides derivados) para la
   * vista previa — misma fusión que hace el backend en `_tema_del_evento`,
   * calculada aquí en cliente para no depender de un endpoint nuevo. */
  protected readonly tokensDePreview = computed(() => {
    const base = this.plantillaActiva()?.tokens ?? { dark: {}, light: {} };
    const overrides = this.evento()?.theme_overrides;
    if (!overrides) {
      return base;
    }
    const paleta = overrides.accent ? derivarPaletaDeAcento(overrides.accent) : null;
    const combinar = (modo: 'dark' | 'light'): Record<string, string> => {
      const combinado = { ...base[modo] };
      if (paleta) {
        Object.assign(combinado, paleta[modo]);
      }
      if (overrides['font-display']) {
        combinado['font-display'] = overrides['font-display'];
      }
      if (overrides['font-body']) {
        combinado['font-body'] = overrides['font-body'];
      }
      return combinado;
    };
    return { dark: combinar('dark'), light: combinar('light') };
  });

  ngOnInit(): void {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set(null);
    try {
      const [plantillas, branding, evento] = await Promise.all([
        firstValueFrom(
          this.http.get<PlantillaDeTema[]>(this.api.url('/organizations/me/theme-templates')),
        ),
        firstValueFrom(this.http.get<BrandingDiseno>(this.api.url('/organizations/me/branding'))),
        firstValueFrom(this.http.get<EventoDiseno>(this.api.url(`/events/${this.eventId()}`))),
      ]);
      this.plantillas.set(plantillas);
      this.brandingThemeId.set(branding.theme_template_id);
      this.evento.set(evento);
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.cargando.set(false);
    }
  }

  protected modoDeMiniatura(plantilla: PlantillaDeTema): 'dark' | 'light' {
    return plantilla.default_mode === 'dark' ? 'dark' : 'light';
  }

  protected elegirPlantilla(plantilla: PlantillaDeTema): void {
    if (plantilla.id === this.plantillaActivaId()) {
      return;
    }
    this.encolar({ tipo: 'plantilla', plantillaId: plantilla.id });
  }

  protected alCambiarColor(evento: Event): void {
    const hex = (evento.target as HTMLInputElement).value.trim();
    if (!colorTieneCromaSuficiente(hex)) {
      this.error.set(this.transloco.translate('admin.events.design.colorAcromatico'));
      return;
    }
    this.error.set(null);
    this.colorPendiente = hex;
    if (this.temporizadorColor) {
      clearTimeout(this.temporizadorColor);
    }
    this.temporizadorColor = setTimeout(() => {
      this.temporizadorColor = null;
      const valor = this.colorPendiente;
      this.colorPendiente = null;
      if (valor) {
        this.encolar({
          tipo: 'personalizar',
          overrides: { ...this.overridesEnCurso(), accent: valor },
        });
      }
    }, 400);
  }

  protected alCambiarFuenteTitulo(familia: string): void {
    this.vaciarDebounceDeColor();
    this.encolar({
      tipo: 'personalizar',
      overrides: { ...this.overridesEnCurso(), 'font-display': familia },
    });
  }

  protected alCambiarFuenteTexto(familia: string): void {
    this.vaciarDebounceDeColor();
    this.encolar({
      tipo: 'personalizar',
      overrides: { ...this.overridesEnCurso(), 'font-body': familia },
    });
  }

  /** Si hay un color a medio debounce, lo envía YA en vez de perderlo —
   * cambiar de tarjeta o de fuente no debe descartar un color pendiente. */
  private vaciarDebounceDeColor(): void {
    if (!this.temporizadorColor) {
      return;
    }
    clearTimeout(this.temporizadorColor);
    this.temporizadorColor = null;
    const valor = this.colorPendiente;
    this.colorPendiente = null;
    if (valor) {
      this.encolar({
        tipo: 'personalizar',
        overrides: { ...this.overridesEnCurso(), accent: valor },
      });
    }
  }

  /** Últimos overrides "conocidos" desde el punto de vista del usuario:
   * los ya confirmados por el servidor, fusionados con lo que haya en vuelo
   * o en cola todavía sin respuesta. Sin esto, cambiar dos campos seguidos
   * (p. ej. color y luego fuente) antes de que llegue la respuesta del
   * primer PATCH perdería el primer cambio, porque `evento()` aún no lo
   * refleja. No es UI optimista: solo evita perder la intención del usuario
   * al construir el payload del siguiente PATCH. */
  private overridesEnCurso(): EventoDiseno['theme_overrides'] {
    const base = { ...(this.evento()?.theme_overrides ?? {}) };
    const enCurso = this.accionEnCurso();
    if (enCurso?.tipo === 'personalizar' || enCurso?.tipo === 'combinada') {
      Object.assign(base, enCurso.overrides);
    }
    if (
      this.accionPendiente?.tipo === 'personalizar' ||
      this.accionPendiente?.tipo === 'combinada'
    ) {
      Object.assign(base, this.accionPendiente.overrides);
    }
    return base;
  }

  /** Cola de un elemento: si ya hay un PATCH en vuelo, esta acción sustituye
   * a la que estuviera esperando. Si la que esperaba era de un tipo
   * distinto (plantilla vs. personalización), no se descarta sin más: se
   * funden en una acción `combinada`, porque el backend admite
   * `theme_template_id` y `theme_overrides` en el mismo PATCH. */
  private encolar(accion: AccionDePersonalizacion): void {
    if (this.accionEnCurso()) {
      this.accionPendiente = this.fusionarConPendiente(accion);
      return;
    }
    void this.enviar(accion);
  }

  private fusionarConPendiente(nueva: AccionDePersonalizacion): AccionDePersonalizacion {
    const previa = this.accionPendiente;
    if (!previa || previa.tipo === nueva.tipo) {
      return nueva;
    }
    const plantillaId =
      nueva.tipo === 'plantilla'
        ? nueva.plantillaId
        : nueva.tipo === 'combinada'
          ? nueva.plantillaId
          : previa.tipo === 'plantilla'
            ? previa.plantillaId
            : previa.tipo === 'combinada'
              ? previa.plantillaId
              : null;
    const overrides =
      nueva.tipo === 'personalizar' || nueva.tipo === 'combinada'
        ? nueva.overrides
        : previa.tipo === 'personalizar' || previa.tipo === 'combinada'
          ? previa.overrides
          : null;
    if (plantillaId === null || overrides === null) {
      return nueva;
    }
    return { tipo: 'combinada', plantillaId, overrides };
  }

  private async enviar(accion: AccionDePersonalizacion): Promise<void> {
    this.accionEnCurso.set(accion);
    this.error.set(null);
    try {
      const payload =
        accion.tipo === 'plantilla'
          ? { theme_template_id: accion.plantillaId }
          : accion.tipo === 'personalizar'
            ? { theme_overrides: accion.overrides }
            : { theme_template_id: accion.plantillaId, theme_overrides: accion.overrides };
      const actualizado = await firstValueFrom(
        this.http.patch<EventoDiseno>(this.api.url(`/events/${this.eventId()}`), payload),
      );
      this.evento.set(actualizado);
      this.mensajeAplicado.set(this.mensajeDeExito(accion));
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.accionEnCurso.set(null);
      const siguiente = this.accionPendiente;
      this.accionPendiente = null;
      if (siguiente) {
        void this.enviar(siguiente);
      }
    }
  }

  private mensajeDeExito(accion: AccionDePersonalizacion): string {
    if (accion.tipo === 'plantilla' || accion.tipo === 'combinada') {
      const nombre = this.plantillas().find((p) => p.id === accion.plantillaId)?.name ?? '';
      return this.transloco.translate('admin.events.design.plantillaAplicada', { nombre });
    }
    return this.transloco.translate('admin.events.design.aplicadoAhora');
  }

  private mensajeDeError(error: unknown): string {
    return error instanceof ApiError
      ? error.message
      : this.transloco.translate('admin.events.design.error');
  }
}
