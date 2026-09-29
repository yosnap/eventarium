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
import { rutaEvento } from '../../../core/routing/rutas-publicas';
import { seoDePagina } from '../../../core/seo/meta.service';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Chip } from '../../../shared/ui/chip';
import { Reveal } from '../../../shared/ui/reveal.directive';

interface PerfilPublico {
  readonly slug: string;
  readonly name: string;
  readonly description: string | null;
  readonly website: string | null;
  readonly address: string | null;
  readonly logo_url: string | null;
  readonly social_links: readonly { readonly kind: string; readonly url: string }[];
}

interface EventoDeLaOrganizacion {
  readonly slug: string;
  readonly cancelled?: boolean;
  readonly organization: { readonly slug: string };
  readonly title: string;
  readonly summary: string | null;
  readonly timezone: string;
  readonly starts_at: string;
  readonly location_name: string | null;
  readonly city: string | null;
}

interface PaginaDeEventos {
  readonly items: readonly EventoDeLaOrganizacion[];
  readonly total: number;
}

type Cuando = 'upcoming' | 'past';

const TAMANO_DE_PAGINA = 12;

/** Nombres propios de las redes conocidas (no se traducen). */
const ETIQUETAS_DE_REDES: Record<string, string> = {
  linkedin: 'LinkedIn',
  github: 'GitHub',
  youtube: 'YouTube',
  x: 'X',
  twitter: 'X',
  instagram: 'Instagram',
  facebook: 'Facebook',
  mastodon: 'Mastodon',
  tiktok: 'TikTok',
  discord: 'Discord',
  telegram: 'Telegram',
  web: 'Web',
};

interface EstadoTransferido {
  readonly perfil: PerfilPublico;
  readonly proximos: PaginaDeEventos;
  readonly pasados: PaginaDeEventos;
}

/**
 * Página pública de una organización (`/{org}`), opt-in: solo existe si la
 * organización activó su página. El perfil trae únicamente los campos que el
 * panel lista como públicos; los eventos son los `published` + `public`,
 * próximos y pasados, paginados con «Ver más».
 */
@Component({
  selector: 'app-organization-public-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, DatePipe, RouterLink, Alert, Button, Chip, Reveal],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p class="ancho-maximo">{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <div class="ancho-maximo">
          <app-alert tone="error">{{
            temporal() ? t('publico.noEncontrada.temporal') : t('publico.organizacion.noEncontrada')
          }}</app-alert>
          <p>
            <a routerLink="/eventos">{{ t('publico.organizacion.verEventos') }}</a>
          </p>
        </div>
      } @else if (perfil(); as p) {
        <header class="cabecera">
          <div class="ancho-maximo cabecera__grid">
            @if (p.logo_url) {
              <img
                class="cabecera__logo"
                [src]="p.logo_url"
                [alt]="p.name"
                width="96"
                height="96"
              />
            }
            <div>
              <p class="etiqueta-acento">{{ t('publico.organizacion.rotulo') }}</p>
              <h1>{{ p.name }}</h1>
              @if (p.description) {
                <p class="cabecera__descripcion">{{ p.description }}</p>
              }
              <ul class="datos">
                @if (p.website) {
                  <li>
                    <a [href]="p.website" rel="noopener noreferrer" target="_blank">{{
                      p.website
                    }}</a>
                  </li>
                }
                @if (p.address) {
                  <li>{{ p.address }}</li>
                }
                @for (enlace of p.social_links; track enlace.url) {
                  <li>
                    <a [href]="enlace.url" rel="noopener noreferrer" target="_blank">{{
                      etiqueta(enlace.kind)
                    }}</a>
                  </li>
                }
              </ul>
            </div>
          </div>
        </header>

        <div class="ancho-maximo secciones">
          @for (seccion of secciones; track seccion.cuando) {
            <section [attr.aria-labelledby]="'org-' + seccion.cuando">
              <h2 [id]="'org-' + seccion.cuando">{{ t(seccion.titulo) }}</h2>
              @let lista = eventosDe(seccion.cuando);
              @if (lista().items.length === 0) {
                <p class="vacio">{{ t(seccion.vacio) }}</p>
              } @else {
                <div class="lista">
                  @for (
                    evento of lista().items;
                    track evento.organization.slug + evento.slug;
                    let i = $index
                  ) {
                    <a
                      class="ev"
                      [routerLink]="rutaEvento(evento.organization.slug, evento.slug)"
                      appReveal
                      [index]="i"
                    >
                      <span class="ev-fecha">
                        <span class="ev-dia">{{
                          evento.starts_at | date: 'dd' : evento.timezone
                        }}</span>
                        <span class="ev-mes">{{
                          evento.starts_at | date: 'MMM y' : evento.timezone
                        }}</span>
                      </span>
                      <span class="ev-cuerpo">
                        <h3>
                          {{ evento.title }}
                          @if (evento.cancelled) {
                            <app-chip tone="apagado">{{
                              t('publico.organizacion.cancelado')
                            }}</app-chip>
                          }
                        </h3>
                        @if (evento.location_name || evento.city) {
                          <span class="ev-meta">
                            {{ evento.location_name
                            }}{{ evento.location_name && evento.city ? ' · ' : ''
                            }}{{ evento.city }}
                          </span>
                        }
                        @if (evento.summary) {
                          <span class="ev-resumen">{{ evento.summary }}</span>
                        }
                      </span>
                    </a>
                  }
                </div>
                @if (lista().items.length < lista().total) {
                  <app-button
                    type="button"
                    variant="secundario"
                    [loading]="cargandoMas() === seccion.cuando"
                    (click)="verMas(seccion.cuando)"
                  >
                    {{ t('publico.organizacion.verMas') }}
                  </app-button>
                }
              }
            </section>
          }
        </div>
      }
    </ng-container>
  `,
  styles: `
    .cabecera {
      padding: var(--sp-8) 0 var(--sp-7);
      border-bottom: 1px solid var(--border);
    }
    .cabecera__grid {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--sp-6);
    }
    .cabecera__logo {
      width: 96px;
      height: 96px;
      object-fit: contain;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
    }
    .etiqueta-acento {
      color: var(--accent);
    }
    .cabecera h1 {
      margin: 6px 0 0;
    }
    .cabecera__descripcion {
      max-width: 60ch;
      color: var(--muted);
      white-space: pre-line;
    }
    .datos {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-2) var(--sp-5);
      margin: var(--sp-4) 0 0;
      padding: 0;
      list-style: none;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .datos a {
      color: var(--accent);
    }
    .secciones {
      display: grid;
      gap: var(--sp-8);
      padding-block: var(--sp-7);
    }
    .vacio {
      color: var(--muted);
    }
    .lista {
      display: grid;
      gap: var(--sp-4);
      margin-bottom: var(--sp-5);
    }
    .ev {
      display: grid;
      grid-template-columns: 104px minmax(0, 1fr);
      align-items: center;
      gap: var(--sp-5);
      padding: var(--sp-5);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      text-decoration: none;
      color: inherit;
      transition:
        border-color 0.15s,
        background-color 0.15s;
    }
    .ev:hover {
      border-color: var(--faint);
      background-color: var(--surface-hi);
    }
    .ev-fecha {
      display: grid;
      justify-items: center;
      padding: 12px 8px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      text-align: center;
    }
    .ev-dia {
      font-family: var(--font-display);
      font-size: 2.1rem;
      line-height: 0.95;
      text-transform: uppercase;
    }
    .ev-mes {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .ev-cuerpo h3 {
      margin: 0;
    }
    .ev-meta,
    .ev-resumen {
      display: block;
      margin-top: var(--sp-2);
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    @media (max-width: 47.5rem) {
      .ev {
        grid-template-columns: 74px minmax(0, 1fr);
        gap: var(--sp-4);
      }
    }
  `,
})
export class OrganizationPublicPage implements OnInit {
  readonly org = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = seoDePagina();
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);

  protected readonly rutaEvento = rutaEvento;
  protected readonly perfil = signal<PerfilPublico | null>(null);
  protected readonly proximos = signal<PaginaDeEventos>({ items: [], total: 0 });
  protected readonly pasados = signal<PaginaDeEventos>({ items: [], total: 0 });
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);
  /** El fallo no fue un 404: no es que la página no exista, sino que no se pudo comprobar. */
  protected readonly temporal = signal(false);
  protected readonly cargandoMas = signal<Cuando | null>(null);

  protected readonly secciones: readonly {
    readonly cuando: Cuando;
    readonly titulo: string;
    readonly vacio: string;
  }[] = [
    {
      cuando: 'upcoming',
      titulo: 'publico.organizacion.proximos',
      vacio: 'publico.organizacion.sinProximos',
    },
    {
      cuando: 'past',
      titulo: 'publico.organizacion.pasados',
      vacio: 'publico.organizacion.sinPasados',
    },
  ];

  protected eventosDe(cuando: Cuando) {
    return cuando === 'upcoming' ? this.proximos : this.pasados;
  }

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  protected etiqueta(tipo: string): string {
    return ETIQUETAS_DE_REDES[tipo.toLowerCase()] ?? tipo.replace(/\b\w/g, (l) => l.toUpperCase());
  }

  private urlEventos(cuando: Cuando, offset: number): string {
    return this.api.url(
      `/public/organizations/${this.org()}/events?when=${cuando}&limit=${TAMANO_DE_PAGINA}&offset=${offset}`,
    );
  }

  private pedirEventos(cuando: Cuando, offset: number): Promise<PaginaDeEventos> {
    return firstValueFrom(
      this.http.get<PaginaDeEventos>(this.urlEventos(cuando, offset), {
        headers: this.api.serverForwardHeaders(),
      }),
    );
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<EstadoTransferido>(`organizacion-publica:${this.org()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      this.cargando.set(false);
      return;
    }
    try {
      const [perfil, proximos, pasados] = await Promise.all([
        firstValueFrom(
          this.http.get<PerfilPublico>(this.api.url(`/public/organizations/${this.org()}`), {
            headers: this.api.serverForwardHeaders(),
          }),
        ),
        this.pedirEventos('upcoming', 0),
        this.pedirEventos('past', 0),
      ]);
      const estado = { perfil, proximos, pasados };
      this.aplicar(estado);
      if (this.api.isServer) {
        this.transferState.set(clave, estado);
      }
    } catch (error) {
      this.noEncontrado.set(true);
      if ((error as { status?: number }).status === 404) {
        this.notFound.mark();
      } else {
        this.temporal.set(true);
        this.notFound.markUnavailable();
      }
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicar(estado: EstadoTransferido): void {
    this.perfil.set(estado.perfil);
    this.proximos.set(estado.proximos);
    this.pasados.set(estado.pasados);
    this.seo.set({
      title: estado.perfil.name,
      description:
        estado.perfil.description ??
        this.transloco.translate('publico.organizacion.descripcionPorDefecto', {
          nombre: estado.perfil.name,
        }),
      image: estado.perfil.logo_url,
      canonica: `/${estado.perfil.slug}`,
    });
  }

  protected async verMas(cuando: Cuando): Promise<void> {
    const lista = this.eventosDe(cuando);
    this.cargandoMas.set(cuando);
    try {
      const siguiente = await this.pedirEventos(cuando, lista().items.length);
      lista.update((actual) => ({
        items: [...actual.items, ...siguiente.items],
        total: siguiente.total,
      }));
    } catch {
      // Sin alerta propia: el botón sigue disponible para reintentar.
    } finally {
      this.cargandoMas.set(null);
    }
  }
}
