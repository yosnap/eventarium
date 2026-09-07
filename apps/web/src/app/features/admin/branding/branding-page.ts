import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { checkBrandingContrast } from '../../../core/theming/contrast';
import { ThemingService } from '../../../core/theming/theming.service';
import { TEMPLATE_REGISTRY } from '../../../core/theming/template-registry';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { Textarea } from '../../../shared/ui/textarea';

interface SocialLink {
  kind: string;
  url: string;
}

interface Branding {
  readonly template_key: string;
  readonly colors: Readonly<Record<string, string>>;
  readonly fonts: Readonly<Record<string, string>>;
  readonly social_links: readonly SocialLink[];
  readonly organizer_blurb: string | null;
  readonly logo_url: string | null;
}

// Mismas claves que `DEFAULT_COLORS`/`DEFAULT_FONTS` en `app/modules/tenant/schemas.py`:
// son las que `apply-tokens.ts` traduce a variables CSS y las que comprueba `contrast.ts`.
// Si el branding guardado no trae alguna, se rellena con este valor neutro para que el
// selector de color no empiece en negro.
const CAMPOS_DE_COLOR: readonly { clave: string; porDefecto: string }[] = [
  { clave: 'primary', porDefecto: '#1d4ed8' },
  { clave: 'primary-contrast', porDefecto: '#ffffff' },
  { clave: 'secondary', porDefecto: '#0f766e' },
  { clave: 'surface', porDefecto: '#ffffff' },
  { clave: 'surface-muted', porDefecto: '#f1f5f9' },
  { clave: 'text', porDefecto: '#0f172a' },
  { clave: 'text-muted', porDefecto: '#475569' },
  { clave: 'border', porDefecto: '#cbd5e1' },
  { clave: 'danger', porDefecto: '#b91c1c' },
  { clave: 'success', porDefecto: '#15803d' },
];
const CAMPOS_DE_FUENTE: readonly string[] = ['sans', 'heading'];

const CLAVES_DE_PLANTILLA = Array.from(TEMPLATE_REGISTRY.keys());

const LOGO_MIMES_PERMITIDOS = new Set(['image/png', 'image/jpeg', 'image/webp']);
// Coincide con `max_image_bytes` en `app/core/config.py`: si diverge, el peor caso es
// un rechazo tardío en el servidor con el mismo mensaje, no un fallo de seguridad.
const LOGO_TAMANO_MAXIMO = 5 * 1024 * 1024;

const HEX_VALIDO = /^#[0-9a-f]{6}$/i;

/**
 * Identidad visual editable: colores, tipografías, plantilla, redes sociales y logo.
 *
 * El estado en edición vive aparte de `ThemingService` (que representa lo ya
 * publicado): así la vista previa del propio panel no cambia mientras se edita, y solo
 * se sincroniza con lo publicado al guardar con éxito.
 */
@Component({
  selector: 'app-branding-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, Textarea],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.branding.titulo') }}</h1>
      <p>{{ t('admin.branding.descripcion') }}</p>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        @for (aviso of avisosDeContraste(); track aviso.primero + aviso.segundo) {
          <app-alert tone="error">
            {{
              t('admin.branding.contrasteInsuficiente', {
                primero: aviso.primero,
                segundo: aviso.segundo,
                ratio: aviso.ratio,
              })
            }}
          </app-alert>
        }

        <form (submit)="guardar($event)" novalidate>
          <div class="tarjetas">
            <app-card [heading]="t('admin.branding.plantilla')">
              <label for="plantilla">{{ t('admin.branding.plantilla') }}</label>
              <select id="plantilla" (change)="alCambiarPlantilla($event)">
                @for (clave of claves; track clave) {
                  <option [value]="clave" [selected]="clave === templateKey()">{{ clave }}</option>
                }
              </select>
            </app-card>

            <app-card [heading]="t('admin.branding.logotipo')">
              @if (previaLogo(); as url) {
                <img [src]="url" [alt]="t('admin.branding.logotipo')" height="64" />
              } @else {
                <p>{{ t('admin.branding.sinLogotipo') }}</p>
              }
              <label class="etiqueta-fichero" for="logo">{{ t('admin.branding.subirLogo') }}</label>
              <input
                id="logo"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                (change)="alSeleccionarLogo($event)"
              />
              @if (errorLogo(); as mensaje) {
                <p class="error">{{ mensaje }}</p>
              }
            </app-card>

            <app-card [heading]="t('admin.branding.colores')">
              <div class="colores">
                @for (campo of camposDeColor; track campo.clave) {
                  <div class="color-fila">
                    <input
                      type="color"
                      class="muestra-editable"
                      [value]="valorColorParaSelector(campo.clave)"
                      (input)="alCambiarColor(campo.clave, colorDelEvento($event))"
                      [attr.aria-label]="t('admin.branding.colorClaves.' + campo.clave)"
                    />
                    <app-input
                      [label]="t('admin.branding.colorClaves.' + campo.clave)"
                      [value]="colors()[campo.clave]"
                      (valueChange)="alCambiarColor(campo.clave, $event)"
                    />
                  </div>
                }
              </div>
            </app-card>

            <app-card [heading]="t('admin.branding.tipografias')">
              @for (clave of camposDeFuente; track clave) {
                <app-input
                  [label]="t('admin.branding.fuenteClaves.' + clave)"
                  [value]="fonts()[clave]"
                  (valueChange)="alCambiarFuente(clave, $event)"
                />
              }
            </app-card>

            <app-card [heading]="t('admin.branding.redesSociales')">
              @for (enlace of socialLinks(); track $index) {
                <div class="red-fila">
                  <app-input
                    [label]="t('admin.branding.tipoDeRed')"
                    [value]="enlace.kind"
                    (valueChange)="alCambiarRed($index, 'kind', $event)"
                  />
                  <app-input
                    [label]="t('admin.branding.urlDeRed')"
                    type="url"
                    [value]="enlace.url"
                    (valueChange)="alCambiarRed($index, 'url', $event)"
                  />
                  <app-button variant="secundario" type="button" (pulsado)="quitarRed($index)">
                    {{ t('admin.branding.quitarRed') }}
                  </app-button>
                </div>
              }
              <app-button variant="secundario" type="button" (pulsado)="anadirRed()">
                {{ t('admin.branding.anadirRed') }}
              </app-button>
            </app-card>

            <app-card [heading]="t('admin.branding.resumenOrganizador')">
              <app-textarea
                [label]="t('admin.branding.resumenOrganizador')"
                [(value)]="organizerBlurb"
              />
            </app-card>
          </div>

          @if (guardado()) {
            <app-alert tone="exito">{{ t('admin.branding.guardado') }}</app-alert>
          }
          @if (error(); as mensaje) {
            <app-alert tone="error" [title]="t('admin.branding.error')">{{ mensaje }}</app-alert>
          }

          <app-button type="submit" [loading]="guardando()">
            {{ guardando() ? t('admin.branding.guardando') : t('comun.guardar') }}
          </app-button>
        </form>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    form {
      display: grid;
      gap: var(--space-lg);
      margin-top: var(--space-md);
    }
    .tarjetas {
      display: grid;
      gap: var(--space-md);
      grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
    }
    select {
      display: block;
      width: 100%;
      margin-top: var(--space-xs);
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 2.75rem;
    }
    .colores {
      display: grid;
      gap: var(--space-sm);
    }
    .color-fila,
    .red-fila {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .color-fila app-input,
    .red-fila app-input {
      flex: 1;
    }
    .muestra-editable {
      width: 2.75rem;
      height: 2.75rem;
      padding: 0;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background: none;
      cursor: pointer;
    }
    .etiqueta-fichero {
      display: block;
      margin-top: var(--space-sm);
      font-weight: 500;
    }
    input[type='file'] {
      margin-top: var(--space-xs);
    }
    .error {
      margin: var(--space-xs) 0 0;
      color: var(--color-danger);
      font-size: 0.875rem;
    }
    img {
      display: block;
      margin-bottom: var(--space-sm);
    }
  `,
})
export class BrandingPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly theming = inject(ThemingService);

  protected readonly claves = CLAVES_DE_PLANTILLA;
  protected readonly camposDeColor = CAMPOS_DE_COLOR;
  protected readonly camposDeFuente = CAMPOS_DE_FUENTE;

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly guardado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errorLogo = signal<string | null>(null);

  protected readonly templateKey = signal(CLAVES_DE_PLANTILLA[0] ?? 'classic');
  protected readonly colors = signal<Record<string, string>>({});
  protected readonly fonts = signal<Record<string, string>>({});
  protected readonly socialLinks = signal<SocialLink[]>([]);
  protected readonly organizerBlurb = signal('');
  protected readonly logoUrlGuardado = signal<string | null>(null);

  private logoPendiente: File | null = null;
  private readonly previaLogoLocal = signal<string | null>(null);
  protected readonly previaLogo = computed(() => this.previaLogoLocal() ?? this.logoUrlGuardado());

  protected readonly avisosDeContraste = computed(() => checkBrandingContrast(this.colors()));

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const branding = await firstValueFrom(
        this.http.get<Branding>(this.api.url('/organizations/me/branding')),
      );
      this.aplicarRespuesta(branding);
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicarRespuesta(branding: Branding): void {
    this.templateKey.set(branding.template_key || CLAVES_DE_PLANTILLA[0] || 'classic');
    const colores: Record<string, string> = {};
    for (const campo of CAMPOS_DE_COLOR) {
      colores[campo.clave] = branding.colors[campo.clave] ?? campo.porDefecto;
    }
    this.colors.set(colores);
    const fuentes: Record<string, string> = {};
    for (const clave of CAMPOS_DE_FUENTE) {
      fuentes[clave] = branding.fonts[clave] ?? '';
    }
    this.fonts.set(fuentes);
    this.socialLinks.set(branding.social_links.map((enlace) => ({ ...enlace })));
    this.organizerBlurb.set(branding.organizer_blurb ?? '');
    this.logoUrlGuardado.set(branding.logo_url);
  }

  protected alCambiarPlantilla(evento: Event): void {
    this.templateKey.set((evento.target as HTMLSelectElement).value);
  }

  protected colorDelEvento(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  /** El selector nativo de color exige `#rrggbb` exacto; un valor a medio escribir se
   * sustituye por un neutro para no romper el control mientras la persona escribe. */
  protected valorColorParaSelector(clave: string): string {
    const valor = this.colors()[clave];
    return HEX_VALIDO.test(valor) ? valor : '#000000';
  }

  protected alCambiarColor(clave: string, valor: string): void {
    this.colors.update((actuales) => ({ ...actuales, [clave]: valor }));
  }

  protected alCambiarFuente(clave: string, valor: string): void {
    this.fonts.update((actuales) => ({ ...actuales, [clave]: valor }));
  }

  protected alCambiarRed(indice: number, campo: 'kind' | 'url', valor: string): void {
    this.socialLinks.update((actuales) =>
      actuales.map((enlace, i) => (i === indice ? { ...enlace, [campo]: valor } : enlace)),
    );
  }

  protected anadirRed(): void {
    this.socialLinks.update((actuales) => [...actuales, { kind: '', url: '' }]);
  }

  protected quitarRed(indice: number): void {
    this.socialLinks.update((actuales) => actuales.filter((_, i) => i !== indice));
  }

  protected alSeleccionarLogo(evento: Event): void {
    this.errorLogo.set(null);
    const fichero = (evento.target as HTMLInputElement).files?.[0] ?? null;
    if (!fichero) {
      return;
    }
    if (!LOGO_MIMES_PERMITIDOS.has(fichero.type)) {
      this.errorLogo.set(this.transloco.translate('admin.branding.logoNoValido'));
      (evento.target as HTMLInputElement).value = '';
      return;
    }
    if (fichero.size > LOGO_TAMANO_MAXIMO) {
      this.errorLogo.set(this.transloco.translate('admin.branding.logoDemasiadoGrande'));
      (evento.target as HTMLInputElement).value = '';
      return;
    }
    this.logoPendiente = fichero;
    this.previaLogoLocal.set(URL.createObjectURL(fichero));
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.guardado.set(false);
    this.error.set(null);

    this.guardando.set(true);
    try {
      let respuesta = await firstValueFrom(
        this.http.put<Branding>(this.api.url('/organizations/me/branding'), {
          template_key: this.templateKey(),
          colors: this.colors(),
          fonts: this.fonts(),
          // Una fila añadida y no rellenada no cuenta como enlace: el backend exige
          // `kind`/`url` no vacíos, y descartarla aquí evita un 422 confuso por un
          // campo que la persona nunca llegó a completar.
          social_links: this.socialLinks().filter(
            (enlace) => enlace.kind.trim() && enlace.url.trim(),
          ),
          organizer_blurb: this.organizerBlurb().trim() || null,
        }),
      );

      if (this.logoPendiente) {
        const datos = new FormData();
        datos.append('fichero', this.logoPendiente);
        respuesta = await firstValueFrom(
          this.http.put<Branding>(this.api.url('/organizations/me/branding/logo'), datos),
        );
        this.logoPendiente = null;
        this.previaLogoLocal.set(null);
      }

      this.aplicarRespuesta(respuesta);
      // La vista previa del panel no cambia mientras se edita (a propósito): solo se
      // sincroniza con `ThemingService` — y por tanto con la web pública — al guardar.
      await this.theming.load();
      this.guardado.set(true);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.branding.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
