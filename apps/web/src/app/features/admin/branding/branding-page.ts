import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { ThemingService } from '../../../core/theming/theming.service';
import { PlantillaDeTema } from '../../../core/theming/theme-template.model';
import { TEMPLATE_REGISTRY } from '../../../core/theming/template-registry';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Textarea } from '../../../shared/ui/textarea';

interface SocialLink {
  kind: string;
  url: string;
}

/** Contrato de `GET`/`PUT /organizations/me/branding` tras la sesión 3 de validación
 * del plan: sin `colors` ni `fonts` (las columnas se retiran en `0015`). */
interface Branding {
  readonly template_key: string;
  readonly theme_template_id: string | null;
  readonly social_links: readonly SocialLink[];
  readonly organizer_blurb: string | null;
  readonly logo_url: string | null;
}

const CLAVES_DE_PLANTILLA_DE_PORTADA = Array.from(TEMPLATE_REGISTRY.keys());

const LOGO_MIMES_PERMITIDOS = new Set(['image/png', 'image/jpeg', 'image/webp']);
// Coincide con `max_image_bytes` en `app/core/config.py`: si diverge, el peor caso es
// un rechazo tardío en el servidor con el mismo mensaje, no un fallo de seguridad.
const LOGO_TAMANO_MAXIMO = 5 * 1024 * 1024;

/**
 * Identidad visual editable: logotipo, plantilla de tema, plantilla de portada, redes
 * sociales y resumen del organizador.
 *
 * Ya no hay ningún campo de color ni de tipografía: la organización elige una
 * plantilla completa del catálogo de la plataforma (sesión 2 de validación del plan),
 * no un acento propio. El nombre de la organización solo se muestra aquí, con enlace a
 * `/admin/organization`: lo edita esa pantalla, no esta (una sola fuente de escritura
 * por dato).
 *
 * El estado en edición vive aparte de `ThemingService` (que representa lo ya
 * publicado): así la vista previa del panel no cambia mientras se edita, y solo se
 * sincroniza con lo publicado al guardar con éxito.
 */
@Component({
  selector: 'app-branding-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card, Textarea],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.branding.titulo') }}</h1>
      <p>{{ t('admin.branding.descripcion') }}</p>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <form (submit)="guardar($event)" novalidate>
          <div class="tarjetas">
            <app-card [heading]="t('admin.branding.logotipo')">
              <p class="nombre-organizacion">
                {{ theming.organizationName() }}
                <a routerLink="/admin/organization">{{ t('admin.branding.editarNombre') }}</a>
              </p>
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

            <app-card [heading]="t('admin.branding.plantillaDePortada')">
              <label for="plantilla-portada">{{ t('admin.branding.plantillaDePortada') }}</label>
              <select id="plantilla-portada" (change)="alCambiarPlantillaDePortada($event)">
                @for (clave of clavesDePortada; track clave) {
                  <option [value]="clave" [selected]="clave === templateKey()">{{ clave }}</option>
                }
              </select>
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

          <fieldset class="plantillas-de-tema">
            <legend>{{ t('admin.branding.plantillaDeTema') }}</legend>
            @for (plantilla of plantillasDeTema(); track plantilla.id) {
              <label class="opcion-plantilla">
                <input
                  type="radio"
                  name="plantilla-de-tema"
                  [value]="plantilla.id"
                  [checked]="plantilla.id === themeTemplateId()"
                  (change)="themeTemplateId.set(plantilla.id)"
                />
                <span class="muestras">
                  @for (modo of modos; track modo) {
                    <span
                      class="muestra"
                      [style.background]="plantilla.tokens[modo]['bg']"
                      [style.color]="plantilla.tokens[modo]['fg']"
                      [style.border-color]="plantilla.tokens[modo]['border']"
                    >
                      <span
                        class="acento"
                        [style.background]="plantilla.tokens[modo]['accent']"
                      ></span>
                    </span>
                  }
                </span>
                <span class="nombre-plantilla">{{ plantilla.name }}</span>
              </label>
            }
            @if (plantillasDeTema().length === 0) {
              <p>{{ t('admin.branding.sinPlantillasDeTema') }}</p>
            }
          </fieldset>

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
    .nombre-organizacion {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-weight: 600;
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
      border: 1px solid var(--color-border);
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
      color: var(--color-danger);
      font-size: 0.875rem;
    }
    img {
      display: block;
      margin-bottom: var(--space-sm);
    }
    .plantillas-de-tema {
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      padding: var(--space-md);
      display: grid;
      gap: var(--space-sm);
    }
    .opcion-plantilla {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      cursor: pointer;
    }
    .muestras {
      display: flex;
      gap: 2px;
    }
    .muestra {
      width: 2rem;
      height: 2rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--color-border);
      display: grid;
      place-items: center;
    }
    .acento {
      width: 0.75rem;
      height: 0.75rem;
      border-radius: 50%;
    }
    .nombre-plantilla {
      font-weight: 500;
    }
  `,
})
export class BrandingPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  protected readonly theming = inject(ThemingService);

  protected readonly clavesDePortada = CLAVES_DE_PLANTILLA_DE_PORTADA;
  protected readonly modos: readonly ('dark' | 'light')[] = ['dark', 'light'];

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly guardado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errorLogo = signal<string | null>(null);

  protected readonly templateKey = signal(CLAVES_DE_PLANTILLA_DE_PORTADA[0] ?? 'classic');
  protected readonly themeTemplateId = signal<string | null>(null);
  protected readonly plantillasDeTema = signal<PlantillaDeTema[]>([]);
  protected readonly socialLinks = signal<SocialLink[]>([]);
  protected readonly organizerBlurb = signal('');
  protected readonly logoUrlGuardado = signal<string | null>(null);

  private logoPendiente: File | null = null;
  private readonly previaLogoLocal = signal<string | null>(null);
  protected readonly previaLogo = computed(() => this.previaLogoLocal() ?? this.logoUrlGuardado());

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const [branding, plantillas] = await Promise.all([
        firstValueFrom(this.http.get<Branding>(this.api.url('/organizations/me/branding'))),
        firstValueFrom(
          this.http.get<PlantillaDeTema[]>(this.api.url('/organizations/me/theme-templates')),
        ),
      ]);
      this.plantillasDeTema.set(plantillas);
      this.aplicarRespuesta(branding);
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicarRespuesta(branding: Branding): void {
    this.templateKey.set(branding.template_key || CLAVES_DE_PLANTILLA_DE_PORTADA[0] || 'classic');
    this.themeTemplateId.set(branding.theme_template_id);
    this.socialLinks.set(branding.social_links.map((enlace) => ({ ...enlace })));
    this.organizerBlurb.set(branding.organizer_blurb ?? '');
    this.logoUrlGuardado.set(branding.logo_url);
  }

  protected alCambiarPlantillaDePortada(evento: Event): void {
    this.templateKey.set((evento.target as HTMLSelectElement).value);
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
