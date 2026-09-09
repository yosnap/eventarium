import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { AvisoDeContraste, comprobarContrasteDePlantilla } from '../../../core/theming/contrast';
import { PlantillaDeTema, TOKENS_DE_PLANTILLA } from '../../../core/theming/theme-template.model';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';

type ModoDeTema = 'dark' | 'light';

interface FormularioDePlantilla {
  id: string | null;
  name: string;
  key: string;
  isDefault: boolean;
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
  imports: [TranslocoDirective, Alert, Button, Card, Input],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.superadmin.plantillas.titulo') }}</h1>
      <p>{{ t('admin.superadmin.plantillas.descripcion') }}</p>

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
            <ul class="lista">
              @for (plantilla of plantillas(); track plantilla.id) {
                <li>
                  <button type="button" class="fila" (click)="editar(plantilla)">
                    <span class="nombre">{{ plantilla.name }}</span>
                    <span class="clave">{{ plantilla.key }}</span>
                  </button>
                </li>
              }
            </ul>
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

            <label class="predeterminada">
              <input
                type="checkbox"
                [checked]="formulario().isDefault"
                (change)="cambiarIsDefault($event)"
              />
              {{ t('admin.superadmin.plantillas.predeterminada') }}
            </label>
            <p class="predeterminada-pista">
              {{ t('admin.superadmin.plantillas.predeterminadaPista') }}
            </p>

            @for (modo of modos; track modo) {
              <fieldset class="modo">
                <legend>{{ t('admin.superadmin.plantillas.modo.' + modo) }}</legend>
                <div class="tokens">
                  @for (token of tokens; track token) {
                    <div class="token-fila">
                      <input
                        type="color"
                        class="muestra"
                        [value]="valorParaSelector(modo, token)"
                        (input)="cambiarToken(modo, token, colorDelEvento($event))"
                        [attr.aria-label]="token"
                      />
                      <app-input
                        [fieldId]="'token-' + modo + '-' + token"
                        [label]="token"
                        [value]="formulario().tokens[modo][token]"
                        (valueChange)="cambiarToken(modo, token, $event)"
                      />
                    </div>
                  }
                </div>
              </fieldset>
            }

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
    .lista {
      list-style: none;
      margin: 0 0 var(--space-md);
      padding: 0;
      display: grid;
      gap: var(--space-xs);
    }
    .fila {
      display: flex;
      justify-content: space-between;
      width: 100%;
      padding: var(--space-sm) var(--space-md);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: none;
      cursor: pointer;
      font: inherit;
      color: var(--color-text);
    }
    .clave {
      color: var(--color-text-muted);
      font-size: 0.875rem;
    }
    form {
      display: grid;
      gap: var(--space-lg);
    }
    .modo {
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      padding: var(--space-md);
    }
    .tokens {
      display: grid;
      gap: var(--space-sm);
      margin-top: var(--space-sm);
    }
    .token-fila {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .token-fila app-input {
      flex: 1;
    }
    .muestra {
      width: 2.5rem;
      height: 2.5rem;
      padding: 0;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: none;
      cursor: pointer;
    }
    .avisos {
      border: 1px solid var(--color-danger);
      border-radius: var(--radius-md);
      padding: var(--space-md);
      color: var(--color-danger);
    }
    .avisos ul {
      margin: var(--space-xs) 0 0;
      padding-left: 1.25rem;
    }
    .clave-inmutable {
      margin: 0;
      color: var(--color-text-muted);
    }
    .predeterminada {
      display: flex;
      align-items: center;
      gap: var(--space-xs);
      cursor: pointer;
    }
    .predeterminada-pista {
      margin: calc(-1 * var(--space-sm)) 0 0;
      color: var(--color-text-muted);
      font-size: 0.8125rem;
    }
  `,
})
export class ThemeTemplatesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly modos: readonly ModoDeTema[] = ['dark', 'light'];
  protected readonly tokens = TOKENS_DE_PLANTILLA;

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

  protected cambiarIsDefault(evento: Event): void {
    const marcada = (evento.target as HTMLInputElement).checked;
    this.formulario.update((actual) => ({ ...actual, isDefault: marcada }));
  }

  protected colorDelEvento(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  /** El selector nativo de color exige `#rrggbb` exacto; un valor a medio escribir u
   * `oklch()` no lo cumple, así que se sustituye por un neutro para no romper el
   * control mientras la persona escribe un valor válido de otro formato. */
  protected valorParaSelector(modo: ModoDeTema, token: string): string {
    const valor = this.formulario().tokens[modo][token] ?? '';
    return /^#[0-9a-f]{6}$/i.test(valor) ? valor : '#000000';
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
            }),
          )
        : await firstValueFrom(
            this.http.post<PlantillaDeTema>(this.api.url('/admin/theme-templates'), {
              key: actual.key.trim(),
              name: actual.name,
              tokens: actual.tokens,
              is_default: actual.isDefault,
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
