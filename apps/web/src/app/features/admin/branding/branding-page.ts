import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { ThemingService } from '../../../core/theming/theming.service';
import { PlantillaDeTema } from '../../../core/theming/theme-template.model';
import { Alert } from '../../../shared/ui/alert';
import { PageHeader } from '../../../shared/ui/page-header';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Textarea } from '../../../shared/ui/textarea';
import { ThemeTemplatePreview } from '../superadmin/theme-template-preview';
import { MediaPicker } from '../../../shared/ui/media-picker';

interface SocialLink {
  kind: string;
  url: string;
}

/** Igual que en `organization-page.ts`: solo se usan los campos que hacen falta aquí. */
interface Organizacion {
  readonly name: string;
}

/** Contrato de `GET`/`PUT /organizations/me/branding` tras la sesión 3 de validación
 * del plan: sin `colors` ni `fonts` (las columnas se retiran en `0015`). Sin
 * `template_key` tampoco (fase 6 del plan de organización sin dominio: sin
 * portada por organización, la plantilla de portada dejó de existir). */
interface Branding {
  readonly theme_template_id: string | null;
  readonly social_links: readonly SocialLink[];
  readonly organizer_blurb: string | null;
  readonly logo_url: string | null;
}

const LOGO_MIMES_PERMITIDOS = new Set(['image/png', 'image/jpeg', 'image/webp']);
// Coincide con `max_image_bytes` en `app/core/config.py`: si diverge, el peor caso es
// un rechazo tardío en el servidor con el mismo mensaje, no un fallo de seguridad.
const LOGO_TAMANO_MAXIMO = 5 * 1024 * 1024;

/**
 * Identidad visual editable: logotipo, plantilla de tema, redes sociales y
 * resumen del organizador.
 *
 * Ya no hay ningún campo de color ni de tipografía: la organización elige una
 * plantilla completa del catálogo de la plataforma (sesión 2 de validación del plan),
 * no un acento propio. El nombre de la organización solo se muestra aquí, con enlace a
 * `/dashboard/organization`: lo edita esa pantalla, no esta (una sola fuente de
 * escritura por dato).
 *
 * El estado en edición vive aparte de `ThemingService` (que representa lo ya
 * publicado): así la vista previa del panel no cambia mientras se edita, y solo se
 * sincroniza con lo publicado al guardar con éxito.
 */
@Component({
  selector: 'app-branding-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    Alert,
    Button,
    Card,
    PageHeader,
    Textarea,
    MediaPicker,
    ThemeTemplatePreview,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.branding.rotulo')">
        {{ t('admin.branding.titulo') }}
        <app-button
          acciones
          type="submit"
          [form]="'form-branding'"
          [disabled]="cargando() || !!errorDeCarga()"
          [loading]="guardando()"
        >
          {{ guardando() ? t('admin.branding.guardando') : t('comun.guardar') }}
        </app-button>
      </app-page-header>
      <p class="descripcion">{{ t('admin.branding.descripcion') }}</p>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (errorDeCarga(); as mensaje) {
        <app-alert tone="error" [title]="t('admin.branding.error')">{{ mensaje }}</app-alert>
      } @else {
        <form id="form-branding" (submit)="guardar($event)" novalidate>
          <div class="tarjetas">
            <app-card [heading]="t('admin.branding.logotipo')">
              <p class="nombre-organizacion">
                {{ nombreOrganizacion() }}
                <a routerLink="/dashboard/organization">{{ t('admin.branding.editarNombre') }}</a>
              </p>
              <app-media-picker
                [etiqueta]="t('admin.branding.logotipo')"
                aceptados="image/png,image/jpeg,image/webp"
                [url]="previaLogo()"
                [permitirUrl]="false"
                [permitirQuitar]="false"
                (ficheroElegido)="alSeleccionarLogo($event)"
              />
              @if (errorLogo(); as mensaje) {
                <p class="error">{{ mensaje }}</p>
              }
            </app-card>

            <app-card [heading]="t('admin.branding.redesSociales')">
              @for (enlace of socialLinks(); track $index) {
                <div class="red-fila">
                  <label
                    >{{ t('admin.branding.tipoDeRed') }}
                    <input
                      type="text"
                      [value]="enlace.kind"
                      (input)="alCambiarRed($index, 'kind', inputDelEvento($event))"
                    />
                  </label>
                  <label
                    >{{ t('admin.branding.urlDeRed') }}
                    <input
                      type="url"
                      [value]="enlace.url"
                      (input)="alCambiarRed($index, 'url', inputDelEvento($event))"
                    />
                  </label>
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

          <div class="plantillas" [attr.aria-label]="t('admin.branding.plantillaDeTema')">
            @for (plantilla of plantillasDeTema(); track plantilla.id) {
              <button
                type="button"
                class="plantilla-tarjeta"
                [class.plantilla-activa]="plantilla.id === themeTemplateId()"
                [attr.aria-pressed]="plantilla.id === themeTemplateId()"
                (click)="themeTemplateId.set(plantilla.id)"
              >
                <span class="plantilla-minis">
                  <span class="plantilla-mini-marco">
                    <app-theme-template-preview
                      class="plantilla-miniatura"
                      [tokens]="plantilla.tokens"
                      modo="dark"
                    />
                  </span>
                  <span class="plantilla-mini-marco">
                    <app-theme-template-preview
                      class="plantilla-miniatura"
                      [tokens]="plantilla.tokens"
                      modo="light"
                    />
                  </span>
                </span>
                <span class="plantilla-nombre">{{ plantilla.name }}</span>
              </button>
            }
            @if (plantillasDeTema().length === 0) {
              <p>{{ t('admin.branding.sinPlantillasDeTema') }}</p>
            }
          </div>

          @if (guardado()) {
            <app-alert tone="exito">{{ t('admin.branding.guardado') }}</app-alert>
          }
          @if (error(); as mensaje) {
            <app-alert tone="error" [title]="t('admin.branding.error')">{{ mensaje }}</app-alert>
          }
        </form>
      }
    </ng-container>
  `,
  styles: `
    .descripcion {
      margin: 0 0 var(--sp-5);
      color: var(--muted);
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
    .nombre-organizacion {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-weight: 600;
    }
    .red-fila {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin-bottom: var(--space-sm);
    }
    .red-fila label {
      flex: 1;
      display: grid;
      gap: var(--space-xs);
      font-size: 0.875rem;
    }
    .red-fila input {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      font: inherit;
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
      color: var(--danger);
      font-size: 0.875rem;
    }
    img {
      display: block;
      margin-bottom: var(--space-sm);
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
    .plantilla-tarjeta:hover {
      border-color: var(--border-strong);
    }
    /* La elegida se marca por borde, no solo por color (WCAG 1.4.1). */
    .plantilla-activa {
      border-color: var(--accent);
      border-width: 2px;
      padding: calc(var(--sp-3) - 1px);
    }
    .plantilla-minis {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-xs);
    }
    /* ThemeTemplatePreview está pensado para su tamaño real (título, chip y
       botón con su tipografía normal, min-height:10rem) — a la anchura de un
       hueco de esta rejilla (mitad de una tarjeta de ~15rem) el texto se corta.
       En vez de reescribir el componente para un tamaño "mini" que no existe,
       se renderiza a un ancho de referencia (--ancho-referencia) y se
       reescala visualmente al hueco real: el marco fija el tamaño final y
       recorta lo que sobre, la miniatura se pinta más grande y se encoge con
       transform, así el texto interno nunca se ve obligado a envolver ni
       desbordar. */
    .plantilla-mini-marco {
      --ancho-referencia: 13rem;
      --factor-escala: 0.62;
      overflow: hidden;
      border-radius: var(--radius-md);
      aspect-ratio: 7 / 5;
    }
    .plantilla-miniatura {
      display: block;
      width: var(--ancho-referencia);
      transform: scale(var(--factor-escala));
      transform-origin: top left;
      pointer-events: none;
    }
    .plantilla-nombre {
      font-weight: 500;
    }
  `,
})
export class BrandingPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly theming = inject(ThemingService);

  protected readonly modos: readonly ('dark' | 'light')[] = ['dark', 'light'];

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly guardado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errorLogo = signal<string | null>(null);
  protected readonly errorDeCarga = signal<string | null>(null);

  protected readonly themeTemplateId = signal<string | null>(null);
  protected readonly plantillasDeTema = signal<PlantillaDeTema[]>([]);
  protected readonly socialLinks = signal<SocialLink[]>([]);
  protected readonly organizerBlurb = signal('');
  protected readonly logoUrlGuardado = signal<string | null>(null);
  protected readonly nombreOrganizacion = signal('');

  private logoPendiente: File | null = null;
  private readonly previaLogoLocal = signal<string | null>(null);
  protected readonly previaLogo = computed(() => this.previaLogoLocal() ?? this.logoUrlGuardado());

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const [organizacion, branding, plantillas] = await Promise.all([
        firstValueFrom(this.http.get<Organizacion>(this.api.url('/organizations/me'))),
        firstValueFrom(this.http.get<Branding>(this.api.url('/organizations/me/branding'))),
        firstValueFrom(
          this.http.get<PlantillaDeTema[]>(this.api.url('/organizations/me/theme-templates')),
        ),
      ]);
      this.nombreOrganizacion.set(organizacion.name);
      this.plantillasDeTema.set(plantillas);
      this.aplicarRespuesta(branding);
    } catch (error) {
      // `errorDeCarga` sustituye al formulario entero en la plantilla: si cualquiera
      // de los tres GET falla, el formulario no debe quedar enviable con valores por
      // defecto que sobrescribirían el branding real al guardar.
      this.errorDeCarga.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.branding.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicarRespuesta(branding: Branding): void {
    this.themeTemplateId.set(branding.theme_template_id);
    this.socialLinks.set(branding.social_links.map((enlace) => ({ ...enlace })));
    this.organizerBlurb.set(branding.organizer_blurb ?? '');
    this.logoUrlGuardado.set(branding.logo_url);
  }

  protected colorDelEvento(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  protected inputDelEvento(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
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

  protected alSeleccionarLogo(fichero: File): void {
    this.errorLogo.set(null);
    if (!LOGO_MIMES_PERMITIDOS.has(fichero.type)) {
      this.errorLogo.set(this.transloco.translate('admin.branding.logoNoValido'));
      return;
    }
    if (fichero.size > LOGO_TAMANO_MAXIMO) {
      this.errorLogo.set(this.transloco.translate('admin.branding.logoDemasiadoGrande'));
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
          theme_template_id: this.themeTemplateId(),
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
