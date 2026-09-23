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

/** Clave propia: `events-list-page.ts` usa `public-events-list` y la borra al
 * consumirla; compartirla dejaría a una de las dos páginas sin estado. */
const CLAVE = makeStateKey<EventoEnDirecto[]>('public-events-landing');

export function estaEnDirecto(evento: EventoEnDirecto, ahora: number): boolean {
  return Date.parse(evento.starts_at) <= ahora && ahora <= Date.parse(evento.ends_at);
}

/**
 * Eventos cuya ventana `starts_at`–`ends_at` cubre el instante actual.
 *
 * `GET /public/events` devuelve todos los publicados sin filtro temporal, así
 * que el corte se hace aquí. En SSR la petición sale de la IP del contenedor
 * `web` y comparte el cubo del limitador con `/eventos`: un 429 (o cualquier
 * fallo) se trata como «sin eventos» sin romper el render, y el cliente vuelve
 * a pedir tras hidratar si no recibió estado transferido.
 *
 * Solo se transfiere el subconjunto en directo, y el primer render en cliente
 * pinta exactamente ese conjunto: recalcular con el reloj del cliente antes de
 * hidratar produciría un DOM distinto al servido (NG0500). `refrescar()` es lo
 * que recalcula después.
 */
@Injectable({ providedIn: 'root' })
export class EnDirectoService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly pendingTasks = inject(PendingTasks);

  private todos: EventoEnDirecto[] = [];
  private readonly ahora = signal<number | null>(null);
  private readonly transferidos = signal<EventoEnDirecto[] | null>(null);

  readonly cargando = signal(true);
  readonly eventos = computed<EventoEnDirecto[]>(() => {
    const ahora = this.ahora();
    if (ahora === null) {
      return this.transferidos() ?? [];
    }
    return this.todos.filter((evento) => estaEnDirecto(evento, ahora));
  });

  async cargar(): Promise<void> {
    const transferido = this.transferState.get(CLAVE, null);
    if (transferido) {
      this.transferState.remove(CLAVE);
      this.todos = transferido;
      this.transferidos.set(transferido);
      this.cargando.set(false);
      return;
    }

    const finalizar = this.pendingTasks.add();
    try {
      this.todos = await firstValueFrom(
        this.http.get<EventoEnDirecto[]>(this.api.url('/public/events'), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
    } catch {
      // 429 del limitador compartido, red caída o API parada: la landing no
      // se rompe por la franja; se queda vacía.
      this.todos = [];
    } finally {
      finalizar();
      this.cargando.set(false);
    }

    const enDirecto = this.todos.filter((evento) => estaEnDirecto(evento, Date.now()));
    if (this.api.isServer) {
      this.transferState.set(CLAVE, enDirecto);
      this.transferidos.set(enDirecto);
    } else {
      this.ahora.set(Date.now());
    }
  }

  /** Recalcula con el reloj del cliente. Llamar solo después de hidratar. */
  refrescar(): void {
    this.ahora.set(Date.now());
  }
}
