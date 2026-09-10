import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  computed,
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
import { Alert } from '../../../shared/ui/alert';
import { rolLegible } from './event-page.types';

interface SocialLink {
  readonly kind: string;
  readonly url: string;
}

interface HistoryItem {
  readonly event_slug: string;
  readonly event_title: string;
  readonly session_id: string;
  readonly session_title: string;
  readonly starts_at: string;
  readonly role_key: string;
}

interface PublicSpeakerProfile {
  readonly display_name: string;
  readonly public_slug: string;
  readonly fields: Record<string, string>;
  readonly social_links: readonly SocialLink[];
  readonly history: readonly HistoryItem[];
}

/** Una edición (evento) del historial, con sus sesiones ordenadas por fecha y
 * el año de la más antigua para la cabecera de la línea de tiempo. */
interface EdicionDeHistorial {
  readonly slug: string;
  readonly title: string;
  readonly anio: number;
  readonly masReciente: string;
  readonly sesiones: readonly HistoryItem[];
}

/** Enlaces sociales reales (`account-page.ts:18`, mismo catálogo cerrado que
 * usa el panel para editarlos): sin esas 4 claves, se humaniza el texto, como
 * `rolLegible`. */
const ETIQUETA_ENLACE: Record<string, string> = {
  twitter: 'X / Twitter',
  linkedin: 'LinkedIn',
  instagram: 'Instagram',
  web: 'publico.ponentes.web',
};

function etiquetaEnlace(kind: string, traducir: (clave: string) => string): string {
  const etiqueta = ETIQUETA_ENLACE[kind.toLowerCase()];
  if (!etiqueta) {
    return kind.replace(/\b\w/g, (letra) => letra.toUpperCase());
  }
  return etiqueta.includes('.') ? traducir(etiqueta) : etiqueta;
}

/** Iniciales del monograma (`.mono-mark` de `ponente-perfil.html:76`): hasta
 * dos letras de las primeras dos palabras del nombre, sin foto real posible
 * (`PUBLIC_PROFILE_FIELDS` no tiene ninguna URL de imagen). */
function iniciales(nombre: string): string {
  return nombre
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((palabra) => palabra[0]?.toUpperCase() ?? '')
    .join('');
}

/**
 * Página pública de un ponente, sobre `.top`/`.side`/`.hist`/`.cv` de la
 * referencia (`ponente-perfil.html`): la lista blanca de campos de la fase 3
 * (nunca `profile_data` completo), redes sociales y el historial de sesiones
 * agrupado por edición con enlace a cada una.
 *
 * Huecos de datos reales frente a la referencia, documentados aquí en vez de
 * rellenados con texto inventado: sin foto (solo monograma de iniciales), sin
 * idiomas, sin temas/etiquetas de la bio, sin estado por charla (confirmada/
 * vídeo/materiales — `HistoryItem` no lo trae) y sin CV estructurado por
 * periodos (`fields['curriculum']` es un único bloque de texto libre, no una
 * lista de `{fechas, rol, organización}`).
 */
@Component({
  selector: 'app-speaker-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TranslocoDirective, Alert],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p class="ancho-maximo">{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <p class="ancho-maximo">
          <app-alert tone="error">{{ t('publico.ponentes.noEncontrado') }}</app-alert>
        </p>
      } @else if (perfil(); as perfil) {
        <article class="ancho-maximo">
          <div class="top">
            <div>
              <span class="rotulo-seccion">{{ t('publico.ponentes.perfil') }}</span>
              <div class="who">
                <div class="mono-mark" aria-hidden="true">{{ iniciales(perfil.display_name) }}</div>
                <div>
                  <h1>{{ perfil.display_name }}</h1>
                  @if (perfil.fields['titular']; as titular) {
                    <p class="titular">{{ titular }}</p>
                  }
                  @if (enlaces(perfil, t).length > 0) {
                    <div class="enlaces">
                      @for (enlace of enlaces(perfil, t); track enlace.etiqueta) {
                        <a class="enlace" [href]="enlace.url" rel="noopener noreferrer" target="_blank">
                          {{ enlace.etiqueta }}
                        </a>
                      }
                    </div>
                  }
                </div>
              </div>
            </div>

            <aside class="lateral">
              @if (perfil.fields['empresa']; as empresa) {
                <div class="lateral__fila">
                  <span class="muted">{{ t('publico.ponentes.empresa') }}</span>
                  <span>{{ empresa }}</span>
                </div>
              }
              @if (perfil.fields['contacto']; as contacto) {
                <div class="lateral__fila">
                  <span class="muted">{{ t('publico.ponentes.contacto') }}</span>
                  <span>{{ contacto }}</span>
                </div>
              }
              <div class="lateral__fila">
                <span class="muted">{{ t('publico.ponentes.ediciones') }}</span>
                <span class="num">{{ ediciones().length }}</span>
              </div>
              <div class="lateral__fila">
                <span class="muted">{{ t('publico.ponentes.ponencias') }}</span>
                <span class="num">{{ perfil.history.length }}</span>
              </div>
              <!-- Idiomas: no existe ningún campo equivalente en el backend
                   (ni en PUBLIC_PROFILE_FIELDS ni en el modelo de usuario).
                   Se muestra la fila con el aviso de dato pendiente, sin
                   inventar el valor, mismo criterio que evento-page.ts. -->
              <div class="lateral__fila">
                <span class="muted">{{ t('publico.ponentes.idiomas') }}</span>
                <span class="pendiente">{{ t('publico.eventos.datoPendiente') }}</span>
              </div>
              @if (proximaParticipacion(); as proxima) {
                <div class="lateral__fila">
                  <span class="muted">{{ t('publico.ponentes.proxima') }}</span>
                  <span class="valor-acento">{{ proxima.event_title }}</span>
                </div>
              }
            </aside>
          </div>

          @if (perfil.fields['bio']; as bio) {
            <section>
              <h2>{{ t('publico.ponentes.bio') }}</h2>
              <p class="prosa">{{ bio }}</p>
            </section>
          }

          @if (ediciones().length > 0) {
            <section>
              <h2>{{ t('publico.ponentes.historial') }}</h2>
              <div class="linea">
                @for (edicion of ediciones(); track edicion.slug; let primera = $first) {
                  <article class="edicion" [class.edicion--actual]="primera">
                    <div class="edicion__cabecera">
                      <h3>
                        <a [routerLink]="['/eventos', edicion.slug]">{{ edicion.title }}</a>
                      </h3>
                      <span class="edicion__anio">
                        {{ edicion.anio }} · {{ rolesDeLaEdicion(edicion.sesiones, t) }}
                      </span>
                    </div>
                    <div class="charlas">
                      @for (sesion of edicion.sesiones; track sesion.session_id) {
                        <a
                          class="charla"
                          [routerLink]="['/eventos', edicion.slug, 'sesiones', sesion.session_id]"
                        >
                          {{ sesion.session_title }}
                        </a>
                      }
                    </div>
                  </article>
                }
              </div>
            </section>
          }

          @if (perfil.fields['curriculum']; as curriculum) {
            <!-- Currículum: la referencia (ponente-perfil.html:162-169) lo
                 muestra como una lista de periodos con fecha/rol/organización
                 estructurados; el backend real solo guarda un único bloque de
                 texto libre (campo curriculum), así que se pinta como prosa,
                 no como esa rejilla. -->
            <section>
              <h2>{{ t('publico.ponentes.curriculum') }}</h2>
              <p class="prosa">{{ curriculum }}</p>
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
    /* .top (ponente-perfil.html:13-14): cabecera + panel lateral, apilados
       bajo el punto de corte de la referencia (860px). */
    .top {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(16.25rem, 20rem);
      gap: var(--space-lg);
      align-items: start;
      padding-bottom: var(--space-lg);
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
      gap: var(--space-md);
      align-items: flex-start;
      margin-top: 1.125rem;
    }
    /* .mono-mark (ponente-perfil.html:15-16): monograma de iniciales, único
       "retrato" posible sin un campo real de foto. */
    .mono-mark {
      flex: 0 0 auto;
      width: 6.5rem;
      height: 6.5rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      display: grid;
      place-items: center;
      font-family: var(--font-display);
      font-size: 2.8rem;
      letter-spacing: 0.04em;
      color: var(--muted);
      padding-top: 6px;
    }
    h1 {
      line-height: 1;
    }
    .titular {
      font-size: 1.05rem;
      color: var(--muted);
      margin-top: 10px;
      max-width: 46ch;
    }
    .enlaces {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs);
      margin-top: var(--space-md);
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
    .lateral__fila > span:last-child {
      text-align: right;
      max-width: 65%;
    }
    .num {
      font-family: var(--font-mono);
    }
    .pendiente {
      font-style: italic;
      color: var(--muted);
    }
    .valor-acento {
      color: var(--accent);
      font-weight: 500;
    }
    section {
      padding-top: var(--space-lg);
    }
    section h2 {
      margin-bottom: var(--space-md);
    }
    .prosa {
      max-width: 66ch;
      color: var(--muted);
    }
    /* .hist/.ed (ponente-perfil.html:33-40): línea de tiempo vertical, con la
       edición más reciente resaltada (punto relleno de acento). */
    .linea {
      border-left: 1px solid var(--border);
      margin-left: 9px;
      padding-left: var(--space-lg);
    }
    .edicion {
      position: relative;
      padding: var(--space-md) 0;
      border-bottom: 1px solid var(--border);
    }
    .edicion:last-child {
      border-bottom: 0;
    }
    .edicion::before {
      content: '';
      position: absolute;
      left: calc(-1 * var(--space-lg) - 5px);
      top: calc(var(--space-md) + 8px);
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background-color: var(--bg);
      border: 1px solid var(--faint);
    }
    .edicion--actual::before {
      background-color: var(--accent);
      border-color: var(--accent);
    }
    .edicion__cabecera {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
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
    .charlas {
      margin-top: var(--space-sm);
      display: grid;
      gap: 10px;
    }
    .charla {
      display: block;
      padding: 11px 14px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      color: inherit;
    }
  `,
})
export class SpeakerPage implements OnInit {
  readonly publicSlug = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);

  protected readonly perfil = signal<PublicSpeakerProfile | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);

  protected readonly iniciales = iniciales;

  /** Edición = evento agrupador de sesiones, más reciente primero — la
   * primera de la lista es la que se resalta (`.edicion--actual`), igual que
   * la referencia marca 2026 (la más nueva) con el punto relleno. */
  protected readonly ediciones = computed<EdicionDeHistorial[]>(() => {
    const historial = this.perfil()?.history ?? [];
    const porEvento = new Map<string, HistoryItem[]>();
    for (const item of historial) {
      const lista = porEvento.get(item.event_slug);
      if (lista) {
        lista.push(item);
      } else {
        porEvento.set(item.event_slug, [item]);
      }
    }
    const grupos: EdicionDeHistorial[] = [...porEvento.entries()].map(([slug, sesiones]) => {
      const ordenadas = [...sesiones].sort((a, b) => a.starts_at.localeCompare(b.starts_at));
      return {
        slug,
        title: ordenadas[0].event_title,
        anio: new Date(ordenadas[0].starts_at).getFullYear(),
        masReciente: ordenadas[ordenadas.length - 1].starts_at,
        sesiones: ordenadas,
      };
    });
    return grupos.sort((a, b) => b.masReciente.localeCompare(a.masReciente));
  });

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  protected enlaces(
    perfil: PublicSpeakerProfile,
    traducir: (clave: string) => string,
  ): { etiqueta: string; url: string }[] {
    const propios = perfil.fields['web']
      ? [{ etiqueta: this.transloco.translate('publico.ponentes.web'), url: perfil.fields['web'] }]
      : [];
    const sociales = perfil.social_links.map((enlace) => ({
      etiqueta: etiquetaEnlace(enlace.kind, traducir),
      url: enlace.url,
    }));
    return [...propios, ...sociales];
  }

  protected rolesDeLaEdicion(sesiones: readonly HistoryItem[], traducir: (clave: string) => string): string {
    const roles = [...new Set(sesiones.map((sesion) => rolLegible(sesion.role_key, traducir)))];
    if (roles.length <= 1) {
      return roles[0] ?? '';
    }
    const [ultimo, ...resto] = [...roles].reverse();
    return `${resto.reverse().join(', ')} y ${ultimo}`;
  }

  /** Próxima sesión futura del historial, la más cercana en el tiempo; `null`
   * si no hay ninguna (no es un hueco de backend, simplemente no aplica). */
  protected proximaParticipacion(): HistoryItem | null {
    const ahora = Date.now();
    const futuras = (this.perfil()?.history ?? [])
      .filter((sesion) => new Date(sesion.starts_at).getTime() > ahora)
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    return futuras[0] ?? null;
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PublicSpeakerProfile>(`public-speaker:${this.publicSlug()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const perfil = await firstValueFrom(
        this.http.get<PublicSpeakerProfile>(this.api.url(`/public/speakers/${this.publicSlug()}`), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.aplicar(perfil);
      if (this.api.isServer) {
        this.transferState.set(clave, perfil);
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

  private aplicar(perfil: PublicSpeakerProfile): void {
    this.perfil.set(perfil);
    this.seo.set({
      title: perfil.display_name,
      description: perfil.fields['bio'] ?? this.transloco.translate('publico.eventos.sinResumen'),
    });
  }
}
