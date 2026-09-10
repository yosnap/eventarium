import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  inject,
  input,
  makeStateKey,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { iniciales } from '../../../shared/text/iniciales';
import { Alert } from '../../../shared/ui/alert';
import { Breadcrumb, type BreadcrumbItem } from '../../../shared/ui/breadcrumb';
import { Chip } from '../../../shared/ui/chip';
import { Reveal } from '../../../shared/ui/reveal.directive';

type ContributionType = 'monetaria' | 'en_especie';

interface PublicSponsorHistoryItem {
  readonly event_slug: string;
  readonly event_title: string;
  readonly starts_at: string;
  readonly tier_name: string;
}

interface PublicSponsorDetail {
  readonly id: string;
  readonly name: string;
  readonly logo_url: string | null;
  readonly website: string | null;
  readonly contribution_type: ContributionType;
  readonly contribution_description: string | null;
  readonly tier_name: string;
  readonly tier_benefits: string | null;
  readonly event_slug: string;
  readonly event_title: string;
  readonly history: readonly PublicSponsorHistoryItem[];
}

const CLAVE_TIPO_APORTACION: Record<ContributionType, string> = {
  monetaria: 'admin.events.sponsors.tipoMonetaria',
  en_especie: 'admin.events.sponsors.tipoEnEspecie',
};

/**
 * Página pública de un patrocinador, sobre `.top`/`.side` de la referencia
 * (`patrocinador-detalle.html`).
 *
 * Huecos de datos reales frente a la referencia, documentados aquí en vez de
 * rellenados con texto inventado: **nunca el importe de la aportación**
 * (decisión explícita del PRD, ver `PublicSponsor` en el backend — no solo
 * un hueco de dato, una decisión de privacidad), sin fecha de cobro, sin "a
 * qué se destina" la aportación, sin compromisos con su estado de
 * cumplimiento y sin contacto — nada de eso existe en `Sponsor`. El
 * historial entre ediciones sí es real: se deriva de patrocinadores con el
 * mismo nombre en otros eventos publicados de la organización, calculado en
 * el backend (`Sponsor` no tiene identidad propia entre eventos, así que la
 * coincidencia es por nombre, la única señal real disponible).
 */
@Component({
  selector: 'app-sponsor-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert, Breadcrumb, Chip, Reveal],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p class="ancho-maximo">{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <p class="ancho-maximo">
          <app-alert tone="error">{{ t('publico.patrocinador.noEncontrado') }}</app-alert>
        </p>
      } @else if (patrocinador(); as patrocinador) {
        <article class="ancho-maximo">
          <app-breadcrumb
            [items]="migasDePan(patrocinador)"
            [ariaLabel]="t('publico.patrocinador.ruta')"
          />

          <div class="top" appReveal>
            <div>
              <span class="rotulo-seccion">{{ t('publico.patrocinador.rotulo') }}</span>
              <div class="who">
                @if (patrocinador.logo_url) {
                  <img class="marca" [src]="patrocinador.logo_url" [alt]="patrocinador.name" />
                } @else {
                  <div class="marca marca--mono" aria-hidden="true">
                    {{ iniciales(patrocinador.name) }}
                  </div>
                }
                <div>
                  <h1>{{ patrocinador.name }}</h1>
                  <div class="rol">
                    <span class="nivel">{{ patrocinador.tier_name }}</span>
                    <app-chip tone="neutro">{{ t(claveTipo(patrocinador)) }}</app-chip>
                  </div>
                  @if (patrocinador.contribution_description; as descripcion) {
                    <p class="prosa">{{ descripcion }}</p>
                  }
                  @if (patrocinador.website) {
                    <div class="enlaces">
                      <a
                        class="enlace"
                        [href]="patrocinador.website"
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        {{ t('publico.patrocinador.web') }}
                      </a>
                    </div>
                  }
                </div>
              </div>
            </div>

            <aside class="lateral" [attr.aria-label]="t('publico.patrocinador.datosAria')">
              <div class="lateral__fila">
                <span class="muted">{{ t('publico.patrocinador.nivel') }}</span>
                <span>{{ patrocinador.tier_name }}</span>
              </div>
              <div class="lateral__fila">
                <span class="muted">{{ t('publico.patrocinador.aportacion') }}</span>
                <span>{{ t(claveTipo(patrocinador)) }}</span>
              </div>
            </aside>
          </div>

          @if (patrocinador.tier_benefits; as beneficios) {
            <section class="seccion" appReveal>
              <div class="seccion__cabecera">
                <span class="rotulo-seccion">{{ t('publico.patrocinador.beneficios') }}</span>
                <h2>{{ t('publico.patrocinador.beneficios') }}</h2>
              </div>
              <p class="prosa">{{ beneficios }}</p>
            </section>
          }

          @if (patrocinador.history.length > 0) {
            <section class="seccion" appReveal>
              <div class="seccion__cabecera">
                <span class="rotulo-seccion">{{ t('publico.patrocinador.historial') }}</span>
                <h2>{{ t('publico.patrocinador.historial') }}</h2>
              </div>
              <div class="linea">
                @for (edicion of patrocinador.history; track edicion.event_slug) {
                  <article class="edicion">
                    <div class="edicion__cabecera">
                      <h3>
                        <a [routerLink]="['/eventos', edicion.event_slug]">{{
                          edicion.event_title
                        }}</a>
                      </h3>
                      <span class="edicion__anio">
                        {{ edicion.starts_at | date: 'yyyy' }} · {{ edicion.tier_name }}
                      </span>
                    </div>
                  </article>
                }
              </div>
            </section>
          }
        </article>
      }
    </ng-container>
  `,
  styles: `
    .ancho-maximo {
      padding: var(--space-lg) 0;
    }
    .top {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(16.25rem, 20rem);
      gap: var(--sp-7);
      align-items: start;
      margin-top: var(--sp-5);
      padding-bottom: var(--sp-7);
      border-bottom: 1px solid var(--border);
    }
    @media (max-width: 53.75rem) {
      .top {
        grid-template-columns: 1fr;
      }
      .who {
        flex-direction: column;
      }
    }
    .who {
      display: flex;
      gap: var(--sp-5);
      align-items: flex-start;
      margin-top: 1.125rem;
    }
    .marca {
      flex: 0 0 auto;
      width: 6.5rem;
      height: 6.5rem;
      border-radius: var(--radius-md);
      object-fit: contain;
      background-color: var(--surface);
      border: 1px solid var(--border-strong);
    }
    .marca--mono {
      border-color: var(--accent);
      display: grid;
      place-items: center;
      font-family: var(--font-display);
      font-size: 2.1rem;
      letter-spacing: 0.04em;
      color: var(--accent);
      padding-top: 6px;
    }
    h1 {
      line-height: 1;
    }
    .rol {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 14px;
    }
    .nivel {
      font-family: var(--font-display);
      font-size: 1.35rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      line-height: 1;
      color: var(--accent);
    }
    .prosa {
      max-width: 66ch;
      color: var(--muted);
      margin-top: var(--sp-4);
    }
    .enlaces {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-2);
      margin-top: var(--sp-5);
    }
    .enlace {
      display: inline-flex;
      align-items: center;
      min-height: 2.25rem;
      padding: 0 0.8125rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      text-decoration: none;
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      transition:
        background-color 0.15s,
        color 0.15s,
        border-color 0.15s;
    }
    .enlace:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
      border-color: var(--faint);
    }
    .lateral {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
    }
    .lateral__fila {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: baseline;
      gap: var(--space-sm) var(--space-md);
      padding: 13px 1.25rem;
      border-bottom: 1px solid var(--border);
    }
    .lateral__fila:last-child {
      border-bottom: 0;
    }
    .seccion {
      padding-top: var(--sp-7);
    }
    .seccion__cabecera {
      margin-bottom: var(--sp-5);
    }
    .seccion__cabecera h2 {
      margin-top: var(--sp-1);
    }
    .linea {
      border-left: 1px solid var(--border);
      margin-left: 9px;
      padding-left: var(--sp-6);
    }
    .edicion {
      padding: var(--sp-4) 0;
      border-bottom: 1px solid var(--border);
    }
    .edicion:last-child {
      border-bottom: 0;
    }
    .edicion__cabecera {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-3);
      align-items: baseline;
      justify-content: space-between;
    }
    .edicion__cabecera h3 {
      margin: 0;
    }
    .edicion__anio {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.16em;
      color: var(--muted);
      white-space: nowrap;
    }
  `,
})
export class SponsorPage implements OnInit {
  readonly slug = input.required<string>();
  readonly sponsorId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);

  protected readonly patrocinador = signal<PublicSponsorDetail | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);

  protected readonly iniciales = iniciales;

  protected claveTipo(patrocinador: PublicSponsorDetail): string {
    return CLAVE_TIPO_APORTACION[patrocinador.contribution_type];
  }

  /** `.crumb` de la referencia (`patrocinador-detalle.html:97-101`): evento ›
   * Patrocinadores › patrocinador actual, tres niveles exactos, sin un
   * "Eventos" añadido encima — ese nivel extra no está en el prototipo. */
  protected migasDePan(patrocinador: PublicSponsorDetail): BreadcrumbItem[] {
    return [
      { label: patrocinador.event_title, routerLink: ['/eventos', patrocinador.event_slug] },
      {
        label: this.transloco.translate('publico.eventos.patrocinadores.titulo'),
        routerLink: ['/eventos', patrocinador.event_slug],
        fragment: 'patrocinadores-h2',
      },
      { label: patrocinador.name },
    ];
  }

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PublicSponsorDetail>(
      `public-sponsor:${this.slug()}:${this.sponsorId()}`,
    );
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const patrocinador = await firstValueFrom(
        this.http.get<PublicSponsorDetail>(
          this.api.url(`/public/events/${this.slug()}/sponsors/${this.sponsorId()}`),
          { headers: this.api.serverForwardHeaders() },
        ),
      );
      this.aplicar(patrocinador);
      if (this.api.isServer) {
        this.transferState.set(clave, patrocinador);
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        this.noEncontrado.set(true);
        this.notFound.mark();
      } else {
        this.noEncontrado.set(true);
      }
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicar(patrocinador: PublicSponsorDetail): void {
    this.patrocinador.set(patrocinador);
    this.seo.set({
      title: `${patrocinador.name} · ${patrocinador.event_title}`,
      description: this.transloco.translate('publico.patrocinador.rotulo'),
    });
  }
}
