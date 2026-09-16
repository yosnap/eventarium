import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { AvisoDeContraste, comprobarContrasteDePlantilla } from '../../../core/theming/contrast';
import { alfaDe, hexParaSelector, oklchDeHex } from '../../../core/theming/oklch';
import { ThemingService } from '../../../core/theming/theming.service';
import {
  FAMILIAS_POR_TOKEN,
  PlantillaDeTema,
  TOKENS_DE_FUENTE,
  TOKENS_DE_PLANTILLA,
  TOKENS_DE_SOMBRA,
} from '../../../core/theming/theme-template.model';
import { Alert } from '../../../shared/ui/alert';
import { Checkbox } from '../../../shared/ui/checkbox';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { PageHeader } from '../../../shared/ui/page-header';
import { RadioGroup } from '../../../shared/ui/radio';
import { ThemeTemplatePreview } from './theme-template-preview';

type ModoDeTema = 'dark' | 'light';

interface FormularioDePlantilla {
  id: string | null;
  name: string;
  key: string;
  isDefault: boolean;
  defaultMode: 'dark' | 'light';
  tokens: { dark: Record<string, string>; light: Record<string, string> };
}

/** Mismo patrón que `key` en `ThemeTemplateCreate` de `apps/api/.../theme_templates/schemas.py`:
 * minúsculas y dígitos, con guiones simples como separador. */
const PATRON_CLAVE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const LONGITUD_MAXIMA_CLAVE = 40;

/** Slug por defecto a partir del nombre: minúsculas, sin diacríticos, espacios y
 * símbolos convertidos en un único guion. Es solo una propuesta editable, nunca la
 * validación final (esa la hace `PATRON_CLAVE` contra lo que quede en el campo). */
function slugificar(valor: string): string {
  return valor
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, LONGITUD_MAXIMA_CLAVE);
}

function formularioVacio(): FormularioDePlantilla {
  const modoVacio = (): Record<string, string> =>
    Object.fromEntries(TOKENS_DE_PLANTILLA.map((token) => [token, '']));
  return {
    id: null,
    name: '',
    key: '',
    isDefault: false,
    defaultMode: 'light',
    tokens: { dark: modoVacio(), light: modoVacio() },
  };
}

/** Un elemento de `problem.errors` tal y como lo manda `_rechazar_si_incumple_contraste`
 * en `apps/api/.../admin/router.py`: misma forma que `AvisoDeContraste`, salvo que
 * `ratio` siempre es un número (nunca `null`: el servidor solo llega a calcularlo
 * cuando los dos colores del par ya se han parseado). */
function esAvisoDeContrasteDelServidor(valor: unknown): valor is AvisoDeContraste {
  if (typeof valor !== 'object' || valor === null) {
    return false;
  }
  const posible = valor as Record<string, unknown>;
  return (
    typeof posible['primero'] === 'string' &&
    typeof posible['segundo'] === 'string' &&
    (posible['modo'] === 'dark' || posible['modo'] === 'light') &&
    typeof posible['ratio'] === 'number'
  );
}

/** Extrae el detalle de contraste de un 422 del servidor, si el error es de ese tipo.
 * `null` si el error no trae `problem.errors` con esa forma (p. ej. un 409 por clave
 * duplicada, o un fallo de red): esos casos siguen su camino normal por `errorGuardar`. */
function errorDeContrasteDelServidor(error: unknown): readonly AvisoDeContraste[] | null {
  if (!(error instanceof ApiError) || error.status !== 422) {
    return null;
  }
  const errores = error.problem?.['errors'];
  if (!Array.isArray(errores) || errores.length === 0 || !errores.every(esAvisoDeContrasteDelServidor)) {
    return null;
  }
  return errores;
}

function formularioDesdePlantilla(plantilla: PlantillaDeTema): FormularioDePlantilla {
  const base = formularioVacio();
  return {
    id: plantilla.id,
    name: plantilla.name,
    key: plantilla.key,
    isDefault: plantilla.is_default ?? false,
    defaultMode: plantilla.default_mode === 'dark' ? 'dark' : 'light',
    tokens: {
      dark: { ...base.tokens.dark, ...plantilla.tokens.dark },
      light: { ...base.tokens.light, ...plantilla.tokens.light },
    },
  };
}

/**
 * CRUD de plantillas de tema para la superadministración: lista, alta y edición de
 * los dos modos. El bloqueo por contraste da el aviso inmediato mientras se edita; la
 * garantía la da el backend, que valida lo mismo y devuelve 422 (decisión A de la
 * sesión 3 de validación de `plan.md`). El 422 del servidor se muestra en el mismo
 * `role="alert"` que el aviso local: nunca un «error inesperado» genérico.
 */
@Component({
  selector: 'app-theme-templates-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    Alert,
    Button,
    Card,
    Checkbox,
    Input,
    PageHeader,
    RadioGroup,
    ThemeTemplatePreview,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.superadmin.plantillas.rotulo')">
        {{ t('admin.superadmin.plantillas.descripcion') }}
      </app-page-header>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        @if (errorLista(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        <app-card [heading]="t('admin.superadmin.plantillas.catalogo')">
          @if (plantillas().length === 0) {
            <p>{{ t('admin.superadmin.plantillas.sinPlantillas') }}</p>
          } @else {
            <div class="catalogo">
              @for (plantilla of plantillas(); track plantilla.id) {
                <div
                  class="tarjeta"
                  [class.tarjeta-activa]="formulario().id === plantilla.id"
                >
                  <button
                    type="button"
                    class="tarjeta-editar"
                    (click)="editar(plantilla)"
                    [attr.aria-label]="
                      t('admin.superadmin.plantillas.editarNombre', { name: plantilla.name })
                    "
                  >
                    <app-theme-template-preview
                      class="tarjeta-miniatura"
                      [tokens]="plantilla.tokens"
                      [modo]="modoDeMiniatura(plantilla)"
                    />
                  </button>
                  <span class="tarjeta-pie">
                    <span class="tarjeta-nombre">{{ plantilla.name }}</span>
                    @if (plantilla.is_default) {
                      <span class="tarjeta-predeterminada">{{
                        t('admin.superadmin.plantillas.predeterminada')
                      }}</span>
                    }
                  </span>
                  @if (enUsoId() === plantilla.id) {
                    <span class="tarjeta-uso">{{ t('admin.superadmin.plantillas.enUso') }}</span>
                  } @else {
                    <app-button
                      type="button"
                      variant="terciario"
                      [loading]="aplicandoId() === plantilla.id"
                      (pulsado)="usar(plantilla)"
                    >
                      {{ t('admin.superadmin.plantillas.usar') }}
                    </app-button>
                  }
                  @if (errorAplicar(); as mensaje) {
                    <p role="alert" class="error-aplicar">{{ mensaje }}</p>
                  }
                </div>
              }
            </div>
          }
          <app-button type="button" variant="secundario" (pulsado)="nueva()">
            {{ t('admin.superadmin.plantillas.nueva') }}
          </app-button>
        </app-card>

        <app-card
          [heading]="
            formulario().id
              ? t('admin.superadmin.plantillas.editar')
              : t('admin.superadmin.plantillas.crear')
          "
        >
          <form (submit)="guardar($event)" novalidate>
            @if (!formulario().id) {
              <app-button type="button" variant="secundario" (pulsado)="copiarDePorDefecto()">
                {{ t('admin.superadmin.plantillas.copiarDePorDefecto') }}
              </app-button>
            }

            <div class="previsualizacion">
              <div class="preview-modo">
                <span class="rotulo-seccion">{{
                  t('admin.superadmin.plantillas.modo.dark')
                }}</span>
                <app-theme-template-preview
                  [tokens]="tokensEnVivo()"
                  modo="dark"
                />
              </div>
              <div class="preview-modo">
                <span class="rotulo-seccion">{{
                  t('admin.superadmin.plantillas.modo.light')
                }}</span>
                <app-theme-template-preview
                  [tokens]="tokensEnVivo()"
                  modo="light"
                />
              </div>
            </div>

            <app-input
              fieldId="plantilla-nombre"
              [label]="t('admin.superadmin.plantillas.nombre')"
              [required]="true"
              [value]="formulario().name"
              (valueChange)="cambiarNombre($event)"
            />

            @if (formulario().id) {
              <p class="clave-inmutable">
                <strong>{{ t('admin.superadmin.plantillas.claveInmutable') }}:</strong>
                {{ formulario().key }}
              </p>
            } @else {
              <app-input
                fieldId="plantilla-clave"
                [label]="t('admin.superadmin.plantillas.clave')"
                [required]="true"
                [hint]="t('admin.superadmin.plantillas.clavePista')"
                [error]="errorClave()"
                [value]="formulario().key"
                (valueChange)="cambiarClave($event)"
              />
            }

            <app-checkbox
              fieldId="plantilla-predeterminada"
              [label]="t('admin.superadmin.plantillas.predeterminada')"
              [checked]="formulario().isDefault"
              (checkedChange)="cambiarIsDefault($event)"
            />
            <p class="predeterminada-pista">
              {{ t('admin.superadmin.plantillas.predeterminadaPista') }}
            </p>

            <app-radio-group
              nombre="modo-por-defecto"
              [etiqueta]="t('admin.superadmin.plantillas.modoPorDefecto')"
              [opciones]="modosSelector()"
              [valor]="formulario().defaultMode"
              (valorChange)="cambiarModoPorDefecto($event)"
            />

            <div class="tokens" role="table" [attr.aria-label]="t('admin.superadmin.plantillas.tokensTabla')">
              <div class="token-cabecera" role="row">
                <span role="columnheader">{{ t('admin.superadmin.plantillas.token') }}</span>
                <span role="columnheader">{{ t('admin.superadmin.plantillas.modo.dark') }}</span>
                <span role="columnheader">{{ t('admin.superadmin.plantillas.modo.light') }}</span>
              </div>
              @for (token of tokensDeColor; track token) {
                <div class="token-fila" role="row">
                  <span class="token-nombre" role="rowheader">{{ token }}</span>
                  @for (modo of modos; track modo) {
                    <div class="token-modo" role="cell">
                      @if (esColor(token)) {
                        <input
                          type="color"
                          class="selector"
                          [value]="hexParaSelector(formulario().tokens[modo][token] ?? '') ?? '#808080'"
                          (input)="elegirColor(modo, token, $event)"
                          [attr.aria-label]="t('admin.superadmin.plantillas.selectorDe', { token: token })"
                        />
                        <app-input
                          [fieldId]="'token-' + modo + '-' + token"
                          [label]="'token ' + token + ' ' + modo"
                          [etiquetaOculta]="true"
                          [value]="formulario().tokens[modo][token]"
                          (valueChange)="cambiarToken(modo, token, $event)"
                        />
                      } @else {
                        <app-input
                          [fieldId]="'token-' + modo + '-' + token"
                          [label]="'token ' + token + ' ' + modo"
                          [etiquetaOculta]="true"
                          [value]="formulario().tokens[modo][token]"
                          (valueChange)="cambiarToken(modo, token, $event)"
                        />
                      }
                    </div>
                  }
                </div>
              }
            </div>

            <div class="tipografia">
              <app-radio-group
                nombre="fuente-display"
                [etiqueta]="t('admin.superadmin.plantillas.fuenteDisplay')"
                [opciones]="familiasDisplay()"
                [valor]="fuenteDe('font-display')"
                (valorChange)="cambiarFuente('font-display', $event)"
              />
              <app-radio-group
                nombre="fuente-body"
                [etiqueta]="t('admin.superadmin.plantillas.fuenteBody')"
                [opciones]="familiasBody()"
                [valor]="fuenteDe('font-body')"
                (valorChange)="cambiarFuente('font-body', $event)"
              />
            </div>

            @if (avisosAMostrar().length > 0) {
              <div role="alert" class="avisos">
                <p>{{ t('admin.superadmin.plantillas.contrasteInsuficiente') }}</p>
                <ul>
                  @for (
                    aviso of avisosAMostrar();
                    track aviso.modo + aviso.primero + aviso.segundo
                  ) {
                    <li>
                      {{
                        t('admin.superadmin.plantillas.parInsuficiente', {
                          primero: aviso.primero,
                          segundo: aviso.segundo,
                          modo: t('admin.superadmin.plantillas.modo.' + aviso.modo),
                          ratio: aviso.ratio ?? '—',
                        })
                      }}
                    </li>
                  }
                </ul>
              </div>
            }

            @if (errorGuardar(); as mensaje) {
              <app-alert tone="error" [title]="t('admin.superadmin.plantillas.errorGuardar')">
                {{ mensaje }}
              </app-alert>
            }
            @if (guardadoOk()) {
              <app-alert tone="exito">{{ t('admin.superadmin.plantillas.guardado') }}</app-alert>
            }

            <app-button type="submit" [disabled]="formularioInvalido()" [loading]="guardando()">
              {{ t('comun.guardar') }}
            </app-button>
          </form>
        </app-card>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    .catalogo {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
      gap: var(--sp-4);
      margin-bottom: var(--space-md);
    }
    .tarjeta {
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
    .tarjeta:hover {
      border-color: var(--border-strong);
    }
    /* La tarjeta que se está editando, marcada por borde, no solo por color. */
    .tarjeta-activa {
      border-color: var(--accent);
      border-width: 2px;
      padding: calc(var(--sp-3) - 1px);
    }
    .tarjeta-editar {
      display: block;
      width: 100%;
      padding: 0;
      border: none;
      background: none;
      cursor: pointer;
      text-align: left;
    }
    .tarjeta-miniatura {
      pointer-events: none;
    }
    .tarjeta-uso {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .error-aplicar {
      margin: 0;
      color: var(--danger);
      font-size: var(--fs-sm);
    }
    .tarjeta-pie {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-xs);
    }
    .tarjeta-nombre {
      font-weight: 600;
    }
    .tarjeta-predeterminada {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--accent);
    }
    .tipografia {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--sp-4);
    }
    @media (max-width: 48rem) {
      .tipografia {
        grid-template-columns: 1fr;
      }
    }
    .previsualizacion {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--sp-4);
    }
    .preview-modo {
      display: grid;
      gap: var(--space-xs);
    }
    @media (max-width: 48rem) {
      .tipografia {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--sp-4);
    }
    @media (max-width: 48rem) {
      .tipografia {
        grid-template-columns: 1fr;
      }
    }
    .previsualizacion {
        grid-template-columns: 1fr;
      }
    }
    form {
      display: grid;
      gap: var(--space-lg);
    }
    .tokens {
      display: grid;
      gap: var(--space-xs);
    }
    .token-cabecera,
    .token-fila {
      display: grid;
      grid-template-columns: minmax(7rem, 1fr) 1fr 1fr;
      gap: var(--space-sm);
      align-items: center;
    }
    .token-cabecera {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      padding: var(--space-xs) 0;
      border-bottom: 1px solid var(--border);
    }
    .token-nombre {
      font-family: var(--font-mono);
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .token-modo {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .selector {
      flex: 0 0 auto;
      width: 2.25rem;
      height: 2.25rem;
      padding: 0;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: none;
      cursor: pointer;
    }
    .token-modo app-input {
      flex: 1;
    }
    @media (max-width: 48rem) {
      .token-cabecera,
      .token-fila {
        grid-template-columns: 1fr;
      }
      .token-nombre {
        border-bottom: 1px dashed var(--border);
        padding-bottom: var(--space-xs);
      }
    }
    .muestra {
      flex-shrink: 0;
      width: 2.5rem;
      height: 2.5rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface);
    }
    .avisos {
      border: 1px solid var(--danger);
      border-radius: var(--radius-md);
      padding: var(--space-md);
      color: var(--danger);
    }
    .avisos ul {
      margin: var(--space-xs) 0 0;
      padding-left: 1.25rem;
    }
    .clave-inmutable {
      margin: 0;
      color: var(--muted);
    }
    .predeterminada-pista {
      margin: calc(-1 * var(--space-sm)) 0 0;
      color: var(--muted);
      font-size: 0.8125rem;
    }
  `,
})
export class ThemeTemplatesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly theming = inject(ThemingService);

  protected readonly modos: readonly ModoDeTema[] = ['dark', 'light'];
  /** Los tokens que pinta la tabla de colores: sin sombras ni fuentes, que
   * tienen su propia sección de edición. */
  protected readonly tokensDeColor = TOKENS_DE_PLANTILLA.filter(
    (token) => !TOKENS_DE_SOMBRA.includes(token) && !TOKENS_DE_FUENTE.includes(token),
  );

  /** Las familias seleccionables de cada token tipográfico, ya traducidas. */
  protected readonly familiasDisplay = computed<readonly { valor: string; etiqueta: string }[]>(
    () => FAMILIAS_POR_TOKEN['font-display'].map((familia) => ({ valor: familia, etiqueta: familia })),
  );

  protected readonly familiasBody = computed<readonly { valor: string; etiqueta: string }[]>(
    () => FAMILIAS_POR_TOKEN['font-body'].map((familia) => ({ valor: familia, etiqueta: familia })),
  );

  /** La familia elegida de un token tipográfico (vive en ambos modos igual). */
  protected fuenteDe(token: string): string {
    return this.formulario().tokens['dark'][token] ?? '';
  }

  /** Cambia un token tipográfico en los dos modos a la vez: la tipografía no
   * cambia con el tema. */
  protected cambiarFuente(token: string, familia: string): void {
    this.formulario.update((actual) => ({
      ...actual,
      tokens: {
        dark: { ...actual.tokens.dark, [token]: familia },
        light: { ...actual.tokens.light, [token]: familia },
      },
    }));
  }

  /** La plantilla que la plataforma tiene aplicada ahora mismo. */
  protected readonly enUsoId = computed(() => this.theming.plataforma()?.theme_template_id ?? null);

  /** Id de la plantilla cuya aplicación está en tránsito, para el estado del botón. */
  protected readonly aplicandoId = signal<string | null>(null);

  protected readonly errorAplicar = signal<string | null>(null);

  /**
   * Aplica la plantilla a toda la plataforma: PATCH de identidad (solo el
   * `theme_template_id`, el nombre no se toca) y recarga del branding, que
   * reinyecta los tokens —colores y fuentes— en el documento al instante.
   */
  protected async usar(plantilla: PlantillaDeTema): Promise<void> {
    this.aplicandoId.set(plantilla.id);
    this.errorAplicar.set(null);
    try {
      await firstValueFrom(
        this.http.patch(this.api.url('/admin/identity'), {
          theme_template_id: plantilla.id,
        }),
      );
      await this.theming.load();
    } catch (error) {
      this.errorAplicar.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.superadmin.plantillas.errorAplicar'),
      );
    } finally {
      this.aplicandoId.set(null);
    }
  }

  /** Tokens del formulario para el preview en vivo (lo que se ve es lo que hay). */
  protected readonly tokensEnVivo = computed(() => this.formulario().tokens);

  /** El modo con el que pinta la miniatura del catálogo: el de apertura de la plantilla. */
  protected modoDeMiniatura(plantilla: PlantillaDeTema): 'dark' | 'light' {
    return plantilla.default_mode === 'dark' ? 'dark' : 'light';
  }

  /** Las dos opciones del selector de modo por defecto, ya traducidas. */
  /** Alias protegidos: las funciones importadas no son visibles a la plantilla. */
  protected readonly hexParaSelector = hexParaSelector;

  protected readonly modosSelector = computed<readonly { valor: ModoDeTema; etiqueta: string }[]>(
    () => [
      { valor: 'light', etiqueta: this.transloco.translate('admin.superadmin.plantillas.modo.light') },
      { valor: 'dark', etiqueta: this.transloco.translate('admin.superadmin.plantillas.modo.dark') },
    ],
  );

  protected readonly cargando = signal(true);
  protected readonly errorLista = signal<string | null>(null);
  protected readonly plantillas = signal<PlantillaDeTema[]>([]);

  protected readonly formulario = signal<FormularioDePlantilla>(formularioVacio());
  protected readonly guardando = signal(false);
  protected readonly guardadoOk = signal(false);
  protected readonly errorGuardar = signal<string | null>(null);

  /** Avisos de contraste locales, recalculados en cada cambio de tokens. */
  protected readonly avisos = computed<readonly AvisoDeContraste[]>(() => {
    const actual = this.formulario();
    return [
      ...comprobarContrasteDePlantilla(actual.tokens.dark, 'dark'),
      ...comprobarContrasteDePlantilla(actual.tokens.light, 'light'),
    ];
  });

  /** Incumplimientos que ha devuelto el 422 del servidor en el último intento de
   * guardado. Solo tiene sentido mientras no haya avisos locales más recientes: si los
   * hay, son ellos los que hay que resolver primero. */
  protected readonly errorContrasteServidor = signal<readonly AvisoDeContraste[]>([]);

  /** Lo que se pinta en el `role="alert"` de contraste: los avisos locales si los hay,
   * y si no, el detalle exacto (par/modo/ratio) del último 422 del servidor. */
  protected readonly avisosAMostrar = computed<readonly AvisoDeContraste[]>(() =>
    this.avisos().length > 0 ? this.avisos() : this.errorContrasteServidor(),
  );

  /** Solo se pone a `true` cuando la persona edita la clave a mano: mientras siga en
   * `false` y se esté creando, `cambiarNombre` sigue proponiendo un slug del nombre. */
  private readonly claveEditadaManualmente = signal(false);

  protected readonly errorClave = computed<string | null>(() => {
    const actual = this.formulario();
    if (actual.id) {
      return null; // La clave es inmutable en edición: no se valida aquí ni se muestra.
    }
    const clave = actual.key.trim();
    if (clave.length === 0 || (PATRON_CLAVE.test(clave) && clave.length <= LONGITUD_MAXIMA_CLAVE)) {
      return null;
    }
    return this.transloco.translate('admin.superadmin.plantillas.claveInvalida');
  });

  /** Bloquea el envío: avisos de contraste locales pendientes, o (solo en alta) una
   * clave vacía o con un formato que el backend rechazaría de todos modos. */
  protected readonly formularioInvalido = computed(() => {
    if (this.avisos().length > 0) {
      return true;
    }
    const actual = this.formulario();
    if (actual.id) {
      return false;
    }
    const clave = actual.key.trim();
    return clave.length === 0 || !PATRON_CLAVE.test(clave) || clave.length > LONGITUD_MAXIMA_CLAVE;
  });

  constructor() {
    void this.cargarLista();
  }

  protected nueva(): void {
    this.formulario.set(formularioVacio());
    this.claveEditadaManualmente.set(false);
    this.errorContrasteServidor.set([]);
    this.guardadoOk.set(false);
    this.errorGuardar.set(null);
    // Sin esto, los 42 tokens quedan vacíos hasta que alguien pulse el botón
    // de copiar: guardar así da una pared de avisos de contraste «—:1»
    // (par sin poder calcularse) en vez de un error útil. Punto de partida
    // editable, nunca una vinculación a la plantilla por defecto.
    this.copiarDePorDefecto();
  }

  protected editar(plantilla: PlantillaDeTema): void {
    this.formulario.set(formularioDesdePlantilla(plantilla));
    this.claveEditadaManualmente.set(true); // La clave ya existe y no se puede tocar.
    this.errorContrasteServidor.set([]);
    this.guardadoOk.set(false);
    this.errorGuardar.set(null);
  }

  protected cambiarNombre(valor: string): void {
    this.formulario.update((actual) => ({
      ...actual,
      name: valor,
      key: !actual.id && !this.claveEditadaManualmente() ? slugificar(valor) : actual.key,
    }));
  }

  protected cambiarClave(valor: string): void {
    this.claveEditadaManualmente.set(true);
    this.formulario.update((actual) => ({ ...actual, key: valor.slice(0, LONGITUD_MAXIMA_CLAVE) }));
  }

  protected cambiarIsDefault(marcada: boolean): void {
    this.formulario.update((actual) => ({ ...actual, isDefault: marcada }));
  }

  protected cambiarModoPorDefecto(modo: 'dark' | 'light'): void {
    this.formulario.update((actual) => ({ ...actual, defaultMode: modo }));
  }

  /**
   * Al crear, los tokens parten de la plantilla predeterminada del catálogo
   * (o de la primera que haya): nadie debe rellenar 42 valores desde cero.
   * Es un punto de partida editable, no una vinculación.
   */
  protected copiarDePorDefecto(): void {
    const base = this.plantillas().find((p) => p.is_default) ?? this.plantillas()[0];
    if (!base) {
      return;
    }
    this.formulario.update((actual) => ({
      ...actual,
      tokens: {
        dark: { ...actual.tokens.dark, ...base.tokens.dark },
        light: { ...actual.tokens.light, ...base.tokens.light },
      },
    }));
  }

  /**
   * Al elegir en el selector nativo (solo sabe `#rrggbb`), el token se escribe
   * en `oklch(...)` — el formato del sistema — conservando la alfa que tuviera
   * (los `*-dim` van con transparencia). Las sombras no son colores: su
   * selector se oculta y se editan por texto.
   */
  protected elegirColor(modo: ModoDeTema, token: string, evento: Event): void {
    const hex = (evento.target as HTMLInputElement).value;
    const convertido = oklchDeHex(hex, alfaDe(this.formulario().tokens[modo][token] ?? ''));
    if (convertido) {
      this.cambiarToken(modo, token, convertido);
    }
  }

  protected esColor(token: string): boolean {
    return !TOKENS_DE_SOMBRA.includes(token);
  }

  protected cambiarToken(modo: ModoDeTema, token: string, valor: string): void {
    this.formulario.update((actual) => ({
      ...actual,
      tokens: { ...actual.tokens, [modo]: { ...actual.tokens[modo], [token]: valor } },
    }));
  }

  private async cargarLista(): Promise<void> {
    this.cargando.set(true);
    this.errorLista.set(null);
    try {
      const lista = await firstValueFrom(
        this.http.get<PlantillaDeTema[]>(this.api.url('/admin/theme-templates')),
      );
      this.plantillas.set(lista);
    } catch (error) {
      this.errorLista.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.superadmin.plantillas.errorLista'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    if (this.formularioInvalido()) {
      // El botón ya queda deshabilitado en este caso; esto es una defensa adicional
      // por si el envío llega por otra vía (p. ej. Enter en un campo).
      return;
    }
    this.guardadoOk.set(false);
    this.errorGuardar.set(null);
    this.errorContrasteServidor.set([]);
    this.guardando.set(true);
    try {
      const actual = this.formulario();
      const respuesta = actual.id
        ? await firstValueFrom(
            this.http.patch<PlantillaDeTema>(this.api.url(`/admin/theme-templates/${actual.id}`), {
              name: actual.name,
              tokens: actual.tokens,
              is_default: actual.isDefault,
              default_mode: actual.defaultMode,
            }),
          )
        : await firstValueFrom(
            this.http.post<PlantillaDeTema>(this.api.url('/admin/theme-templates'), {
              key: actual.key.trim(),
              name: actual.name,
              tokens: actual.tokens,
              is_default: actual.isDefault,
              default_mode: actual.defaultMode,
            }),
          );
      this.formulario.set(formularioDesdePlantilla(respuesta));
      this.claveEditadaManualmente.set(true);
      this.guardadoOk.set(true);
      await this.cargarLista();
    } catch (error) {
      // El 422 de contraste del servidor se muestra igual que el aviso local, con el
      // detalle exacto de qué par, modo y ratio han fallado: nunca un genérico «error
      // inesperado» que lo oculte.
      const incumplimientos = errorDeContrasteDelServidor(error);
      if (incumplimientos) {
        this.errorContrasteServidor.set(incumplimientos);
      }
      this.errorGuardar.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.superadmin.plantillas.errorGuardar'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
