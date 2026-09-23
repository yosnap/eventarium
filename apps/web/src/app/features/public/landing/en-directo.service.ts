import { HttpClient } from '@angular/common/http';
import {
  Injectable,
  PendingTasks,
  TransferState,
  computed,
  inject,
  makeStateKey,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';

export type ModoDeUbicacion = 'in_person' | 'online' | 'hybrid';

/** Subconjunto de `PublicEventSummary` que necesita la franja «en directo». */
export interface EventoEnDirecto {
  readonly slug: string;
  readonly title: string;
  readonly cover_url: string | null;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly location_mode: ModoDeUbicacion;
  readonly location_name: string | null;
  readonly city: string | null;
}

interface EstadoTransferido {
  readonly eventos: EventoEnDirecto[];
  /** Reloj del servidor con el que se filtró: el primer render en cliente
   * usa exactamente este instante para pintar lo mismo que el HTML servido. */
  readonly ahora: number;
}

/** Clave propia: `events-list-page.ts` usa `public-events-list` y la borra al
 * consumirla; compartirla dejaría a una de las dos páginas sin estado. */
const CLAVE = makeStateKey<EstadoTransferido>('public-events-landing');

export function estaEnDirecto(evento: EventoEnDirecto, ahora: number): boolean {
  return Date.parse(evento.starts_at) <= ahora && ahora <= Date.parse(evento.ends_at);
}

/**
 * Eventos cuya ventana `starts_at`–`ends_at` cubre el instante actual.
 *
 * `GET /public/events` devuelve todos los publicados sin filtro temporal, así
 * que el corte se hace aquí sobre la lista completa; así `refrescar()` puede
 * incorporar un evento que empieza mientras la página sigue abierta.
 *
 * En SSR la petición sale de la IP del contenedor `web` y comparte el cubo del
 * limitador con `/eventos`: un 429 (o cualquier fallo) se trata como «sin
 * eventos» sin romper el render, y **no** se transfiere nada, para que el
 * cliente vuelva a pedir tras hidratar. Solo una respuesta correcta viaja en
 * `TransferState`, junto con el reloj con el que se filtró: el primer render
 * del cliente usa ese mismo instante (un DOM distinto al servido daría
 * NG0500) y `refrescar()` pasa al reloj del cliente después de hidratar.
 */
@Injectable({ providedIn: 'root' })
export class EnDirectoService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly pendingTasks = inject(PendingTasks);

  private readonly todos = signal<EventoEnDirecto[]>([]);
  private readonly ahora = signal(0);
  private peticion: Promise<void> | null = null;

  readonly cargando = signal(true);
  readonly eventos = computed(() => {
    const ahora = this.ahora();
    return this.todos().filter((evento) => estaEnDirecto(evento, ahora));
  });

  cargar(): Promise<void> {
    const transferido = this.transferState.get(CLAVE, null);
    if (transferido) {
      this.transferState.remove(CLAVE);
      this.todos.set(transferido.eventos);
      this.ahora.set(transferido.ahora);
      this.cargando.set(false);
      return Promise.resolve();
    }
    // Servicio raíz: en una segunda visita por navegación SPA no hay estado
    // transferido; se vuelve a pedir, sin duplicar una petición ya en vuelo.
    this.peticion ??= this.pedir().finally(() => {
      this.peticion = null;
    });
    return this.peticion;
  }

  private async pedir(): Promise<void> {
    this.cargando.set(true);
    const finalizar = this.pendingTasks.add();
    try {
      const eventos = await firstValueFrom(
        this.http.get<EventoEnDirecto[]>(this.api.url('/public/events'), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      const ahora = Date.now();
      this.todos.set(eventos);
      this.ahora.set(ahora);
      if (this.api.isServer) {
        this.transferState.set(CLAVE, { eventos, ahora });
      }
    } catch {
      this.todos.set([]);
      this.ahora.set(Date.now());
    } finally {
      finalizar();
      this.cargando.set(false);
    }
  }

  /** Recalcula con el reloj del cliente. Llamar solo después de hidratar. */
  refrescar(): void {
    this.ahora.set(Date.now());
  }
}
