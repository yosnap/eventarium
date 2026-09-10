import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  computed,
  inject,
  makeStateKey,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { Alert } from '../../../shared/ui/alert';
import { Chip } from '../../../shared/ui/chip';
import { Select, type SelectOption } from '../../../shared/ui/select';

type LocationMode = 'in_person' | 'online' | 'hybrid';
type FiltroModo = 'todos' | LocationMode;
type RegistrationMode = 'free' | 'approval' | 'paid';
type FiltroRegistro = 'todos' | RegistrationMode;

interface PublicEventSummary {
  readonly slug: string;
  readonly title: string;
  readonly summary: string | null;
  readonly cover_url: string | null;
  readonly timezone: string;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly location_mode: LocationMode;
  readonly location_name: string | null;
  readonly city: string | null;
  readonly registration_mode: RegistrationMode;
  readonly capacity: number | null;
  readonly reserved_count: number;
}

const CLAVE = makeStateKey<PublicEventSummary[]>('public-events-list');

const CLAVE_FORMATO: Record<LocationMode, string> = {
  in_person: 'publico.eventos.formato.presencial',
  online: 'publico.eventos.formato.online',
  hybrid: 'publico.eventos.formato.hibrido',
};

const CLAVE_TAG: Record<FiltroModo, string> = {
  todos: 'publico.eventos.filtro.todos',
  in_person: 'publico.eventos.formato.presencial',
  online: 'publico.eventos.formato.online',
  hybrid: 'publico.eventos.formato.hibrido',
};

const MODOS_FILTRABLES: readonly FiltroModo[] = ['todos', 'in_person', 'online', 'hybrid'];

/** Tono del chip de modo de registro, mismo mapeo que `event-page.ts`. */
const CLAVE_REGISTRO: Record<RegistrationMode, { clave: string; tono: 'ok' | 'espera' | 'neutro' }> = {
  free: { clave: 'publico.eventos.registro.gratuita', tono: 'ok' },
  approval: { clave: 'publico.eventos.registro.aprobacion', tono: 'espera' },
  paid: { clave: 'publico.eventos.registro.pago', tono: 'neutro' },
};

const CLAVE_TAG_REGISTRO: Record<FiltroRegistro, string> = {
  todos: 'publico.eventos.filtro.todos',
  free: 'publico.eventos.registro.gratuita',
  approval: 'publico.eventos.registro.aprobacion',
  paid: 'publico.eventos.registro.pago',
};

const REGISTROS_FILTRABLES: readonly FiltroRegistro[] = ['todos', 'free', 'approval', 'paid'];

/** Normaliza una ciudad para comparar/deduplicar sin distinguir mayúsculas ni
 * espacios sobrantes ("Valencia" === " valencia "), sin tocar el valor que se
 * muestra. */
function normalizarCiudad(ciudad: string): string {
  return ciudad.trim().toLocaleLowerCase('es');
}

/**
 * Listado público de eventos publicados de la organización, sobre
 * `.searchbar`/`.toolbar`/`.tags`/`.ev` de la referencia real
 * (`descubrir-eventos.html` del proyecto OpenDesign): buscador de texto,
 * filtro por formato y fila de evento en tres columnas (fecha, cuerpo, chip
 * de formato).
 *
 * El buscador filtra en el cliente sobre los eventos ya cargados (título,
 * resumen, lugar) — no hay endpoint de búsqueda, y no hace falta uno para
 * una lista de este tamaño. Los filtros de etiqueta usan `location_mode` y
 * `registration_mode`, y el select de ciudad usa `city` — los tres son datos
 * reales de `PublicEventSummary`, con las opciones de ciudad calculadas a
 * partir de los eventos cargados (no una lista fija como en la referencia).
 * El lado derecho de cada fila añade el estado real de plazas (`capacity` -
 * `reserved_count`, o "sin límite" si no hay `capacity`) y el modo de
 * registro, sin inventar ningún precio.
 *
 * No se muestra `cover_url` en la fila: la referencia no lleva imagen en
 * este patrón de lista (sí la lleva la ficha del evento).
 */
@Component({
  selector: 'app-events-list-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert, Chip, Select],
  template: `
    <ng-container *transloco="let t">
      <section class="hero">
        <div class="ancho-maximo">
          <p class="rotulo-seccion etiqueta-acento">{{ t('publico.eventos.rotulo') }}</p>
          <h1>{{ t('publico.eventos.listadoTitulo') }}</h1>

          @if (!cargando() && eventos().length > 0) {
            <div class="searchbar" role="search">
              <label class="sr-only" for="q">{{ t('publico.eventos.buscarEtiqueta') }}</label>
              <input
                id="q"
                type="search"
                [placeholder]="t('publico.eventos.buscarPlaceholder')"
                [value]="busqueda()"
                (input)="alBuscar($event)"
              />
              @if (ciudadesDisponibles().length > 0) {
                <app-select
                  fieldId="ciudad"
                  [label]="t('publico.eventos.ciudadEtiqueta')"
                  [options]="opcionesCiudad(t('publico.eventos.ciudadTodas'))"
                  [value]="filtroCiudad()"
                  (valueChange)="filtroCiudad.set($event)"
                />
              }
            </div>
          }
        </div>
      </section>

      <section class="cuerpo">
        <div class="ancho-maximo">
          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          @if (cargando()) {
            <p>{{ t('comun.cargando') }}</p>
          } @else if (eventos().length === 0) {
            <p class="vacio">{{ t('publico.eventos.sinEventos') }}</p>
          } @else {
            <div class="toolbar">
              <span class="rotulo-seccion">{{ t('publico.eventos.filtrarRotulo') }}</span>
              <div class="tags" role="group" [attr.aria-label]="t('publico.eventos.filtrarRotulo')">
                @for (modo of modos; track modo) {
                  <button
                    type="button"
                    class="tag"
                    [attr.aria-pressed]="filtroModo() === modo"
                    (click)="filtroModo.set(modo)"
                  >
                    {{ t(claveTag(modo)) }}
                  </button>
                }
              </div>
              <div
                class="tags"
                role="group"
                [attr.aria-label]="t('publico.eventos.filtrarRegistroRotulo')"
              >
                @for (registro of registros; track registro) {
                  <button
                    type="button"
                    class="tag"
                    [attr.aria-pressed]="filtroRegistro() === registro"
                    (click)="filtroRegistro.set(registro)"
                  >
                    {{ t(claveTagRegistro(registro)) }}
                  </button>
                }
              </div>
              <span class="hint" role="status" aria-live="polite">
                {{ t('publico.eventos.contador', { n: eventosFiltrados().length }) }}
              </span>
            </div>

            @if (eventosFiltrados().length === 0) {
              <p class="vacio">{{ t('publico.eventos.sinResultados') }}</p>
            } @else {
              <div class="lista">
                @for (evento of eventosFiltrados(); track evento.slug) {
                  <a class="ev" [routerLink]="['/eventos', evento.slug]">
                    <span class="ev-fecha">
                      <span class="ev-dia">{{ evento.starts_at | date: 'dd' : evento.timezone }}</span>
                      <span class="ev-mes">{{ evento.starts_at | date: 'MMM' : evento.timezone }}</span>
                    </span>
                    <span class="ev-cuerpo">
                      <h3>{{ evento.title }}</h3>
                      <span class="ev-meta">
                        @if (evento.location_name || evento.city) {
                          <span>
                            {{ evento.location_name }}{{ evento.location_name && evento.city ? ' · ' : '' }}{{
                              evento.city
                            }}
                          </span>
                        }
                        @if (evento.summary) {
                          <span>{{ evento.summary }}</span>
                        }
                      </span>
                    </span>
                    <span class="ev-lado">
                      <span class="ev-lado-chips">
                        <app-chip>{{ t(claveFormato(evento)) }}</app-chip>
                        <app-chip [tone]="claveRegistroTono(evento)">{{
                          t(claveRegistro(evento))
                        }}</app-chip>
                      </span>
                      <span class="ev-plazas">
                        @if (plazasLibres(evento); as plazas) {
                          {{ t('publico.eventos.plazasLibres', { n: plazas }) }}
                        } @else if (evento.capacity === null) {
                          {{ t('publico.eventos.sinLimite') }}
                        } @else {
                          <app-chip tone="apagado">{{ t('publico.eventos.completo') }}</app-chip>
                        }
                      </span>
                    </span>
                  </a>
                }
              </div>
            }
          }
        </div>
      </section>
    </ng-container>
  `,
  styles: `
    /* .hero (descubrir-eventos.html:14-31): rótulo mono en acento sobre el
       titular grande, con el buscador debajo. */
    .hero {
      padding: var(--sp-8) 0 var(--sp-7);
      border-bottom: 1px solid var(--border);
    }
    .etiqueta-acento {
      color: var(--accent);
    }
    .hero h1 {
      margin: 6px 0 0;
    }
    /* .searchbar (descubrir-eventos.html:16-19). */
    .searchbar {
      display: flex;
      margin-top: var(--sp-6);
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      max-width: 32rem;
    }
    .searchbar input {
      flex: 1 1 auto;
      min-height: 44px;
      padding: 0 14px;
      background-color: var(--bg);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      color: var(--fg);
      font: inherit;
    }
    .searchbar input:focus {
      border-color: var(--accent);
      outline: none;
    }
    /* Select de ciudad (app-select): junto al buscador de texto, sin
       estirarse a todo el ancho disponible del .searchbar. */
    .searchbar app-select {
      flex: 0 0 auto;
      min-width: 12rem;
      margin-left: var(--sp-3);
    }
    .cuerpo {
      padding: var(--sp-6) 0 var(--sp-9);
    }
    .vacio {
      color: var(--muted);
    }
    /* .toolbar/.tags (descubrir-eventos.html:20-26). */
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--sp-3);
      padding: var(--sp-5) 0;
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      margin-bottom: var(--sp-6);
    }
    .tags {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .tag {
      min-height: 34px;
      padding: 0 14px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: transparent;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      cursor: pointer;
      transition:
        background-color 0.15s,
        color 0.15s,
        border-color 0.15s;
    }
    .tag:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
      border-color: var(--faint);
    }
    .tag[aria-pressed='true'] {
      background-color: var(--accent);
      border-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
    }
    .toolbar .hint {
      margin-left: auto;
      color: var(--muted);
    }
    .lista {
      display: grid;
      gap: var(--sp-4);
    }
    /* .ev (descubrir-eventos.html:32-35): la fila entera es el enlace, con
       tres columnas — fecha, cuerpo y el lado derecho con el formato. */
    .ev {
      display: grid;
      grid-template-columns: 104px minmax(0, 1fr) auto;
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
    /* .ev__date (descubrir-eventos.html:36-39). */
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
    .ev-meta {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-4);
      margin-top: 8px;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .ev-lado {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: var(--sp-2);
    }
    .ev-lado-chips {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: var(--sp-2);
    }
    .ev-plazas {
      font-size: var(--fs-sm);
      color: var(--muted);
      white-space: nowrap;
    }
    @media (max-width: 47.5rem) {
      .ev {
        grid-template-columns: 74px minmax(0, 1fr);
        gap: var(--sp-4);
      }
      .ev-lado {
        grid-column: 2;
        align-items: flex-start;
      }
      .ev-lado-chips {
        justify-content: flex-start;
      }
    }
  `,
})
export class EventsListPage implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly transloco = inject(TranslocoService);

  protected readonly eventos = signal<PublicEventSummary[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);

  protected readonly busqueda = signal('');
  protected readonly filtroModo = signal<FiltroModo>('todos');
  protected readonly filtroRegistro = signal<FiltroRegistro>('todos');
  protected readonly filtroCiudad = signal('');
  protected readonly modos = MODOS_FILTRABLES;
  protected readonly registros = REGISTROS_FILTRABLES;

  /** Ciudades únicas presentes en los eventos ya cargados, ordenadas
   * alfabéticamente — nunca una lista fija: solo existen las ciudades que de
   * verdad tiene algún evento publicado. La deduplicación ignora mayúsculas y
   * espacios sobrantes ("Valencia"/"valencia" cuentan como la misma ciudad),
   * mostrando siempre la primera grafía vista tal cual se guardó. */
  protected readonly ciudadesDisponibles = computed(() => {
    const vistas = new Map<string, string>();
    for (const evento of this.eventos()) {
      if (!evento.city) continue;
      const clave = normalizarCiudad(evento.city);
      if (!vistas.has(clave)) vistas.set(clave, evento.city);
    }
    return [...vistas.values()].sort((a, b) => a.localeCompare(b, 'es'));
  });

  /** Opciones del select de ciudad, con "todas" como primera opción
   * seleccionable (no un `placeholder` deshabilitado: elegirla vuelve a
   * mostrar todos los eventos, es una opción válida). */
  protected opcionesCiudad(etiquetaTodas: string): SelectOption[] {
    return [
      { value: '', label: etiquetaTodas },
      ...this.ciudadesDisponibles().map((ciudad) => ({ value: ciudad, label: ciudad })),
    ];
  }

  protected readonly eventosFiltrados = computed(() => {
    const texto = this.busqueda().trim().toLowerCase();
    const modo = this.filtroModo();
    const registro = this.filtroRegistro();
    const ciudad = this.filtroCiudad();
    const ciudadNormalizada = ciudad ? normalizarCiudad(ciudad) : '';
    return this.eventos().filter((evento) => {
      if (modo !== 'todos' && evento.location_mode !== modo) return false;
      if (registro !== 'todos' && evento.registration_mode !== registro) return false;
      if (ciudadNormalizada && normalizarCiudad(evento.city ?? '') !== ciudadNormalizada) {
        return false;
      }
      if (!texto) return true;
      const haystack = [evento.title, evento.summary, evento.location_name, evento.city]
        .filter((valor): valor is string => !!valor)
        .join(' ')
        .toLowerCase();
      return haystack.includes(texto);
    });
  });

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  protected alBuscar(evento: Event): void {
    this.busqueda.set((evento.target as HTMLInputElement).value);
  }

  protected claveFormato(evento: PublicEventSummary): string {
    return CLAVE_FORMATO[evento.location_mode];
  }

  protected claveTag(modo: FiltroModo): string {
    return CLAVE_TAG[modo];
  }

  protected claveTagRegistro(registro: FiltroRegistro): string {
    return CLAVE_TAG_REGISTRO[registro];
  }

  protected claveRegistro(evento: PublicEventSummary): string {
    return CLAVE_REGISTRO[evento.registration_mode].clave;
  }

  protected claveRegistroTono(evento: PublicEventSummary): 'ok' | 'espera' | 'neutro' {
    return CLAVE_REGISTRO[evento.registration_mode].tono;
  }

  /** Plazas libres reales: `null` cuando el evento no tiene `capacity` (sin
   * límite, no "cero plazas"); si tiene `capacity`, `capacity - reserved_count`
   * sin bajar nunca de 0 (una sobreventa puntual no se muestra en negativo). */
  protected plazasLibres(evento: PublicEventSummary): number | null {
    if (evento.capacity === null) return null;
    return Math.max(0, evento.capacity - evento.reserved_count);
  }

  private async cargar(): Promise<void> {
    this.seo.set({ title: this.transloco.translate('publico.eventos.listadoTitulo') });

    const transferido = this.transferState.get(CLAVE, null);
    if (transferido) {
      this.transferState.remove(CLAVE);
      this.eventos.set(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const eventos = await firstValueFrom(
        this.http.get<PublicEventSummary[]>(this.api.url('/public/events'), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.eventos.set(eventos);
      if (this.api.isServer) {
        this.transferState.set(CLAVE, eventos);
      }
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('publico.eventos.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }
}
