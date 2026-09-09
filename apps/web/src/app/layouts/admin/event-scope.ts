import { HttpClient } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRouteSnapshot, NavigationEnd, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { filter } from 'rxjs/operators';

import { ApiService } from '../../core/api/api.service';

type RegistrationMode = 'free' | 'approval' | 'paid';

interface EventoResumen {
  readonly title: string;
  readonly registration_mode: RegistrationMode;
}

/**
 * Resuelve el ámbito de evento desde la ruta activa: si el árbol de rutas contiene un
 * parámetro `eventId` o `id` (ambos en uso — `check-in`/`payments` frente a
 * `events/:id`), estamos dentro de un evento, y se carga su nombre y su modo de
 * inscripción para la navegación contextual.
 *
 * Un fallo de red al cargar el nombre **no** debe dejar el panel sin navegación: el
 * consumidor (`AdminNav` vía `AdminShell`) oculta el grupo entero cuando `falloCarga()`
 * es `true`, igual que ya hace el selector de organizaciones con sus propios fallos.
 */
@Injectable({ providedIn: 'root' })
export class EventScope {
  private readonly router = inject(Router);
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  private readonly navegacion = toSignal(
    this.router.events.pipe(filter((evento) => evento instanceof NavigationEnd)),
    { initialValue: null },
  );

  /** `null` cuando la ruta activa no está dentro de ningún evento. */
  readonly eventId = computed(() => {
    this.navegacion();
    return this.idDesdeRuta(this.router.routerState.snapshot.root);
  });

  private readonly cache = new Map<string, EventoResumen>();
  private readonly resumen = signal<EventoResumen | null>(null);
  private readonly cargandoEstado = signal(false);
  private readonly falloEstado = signal(false);

  readonly nombreEvento = computed(() => this.resumen()?.title ?? null);
  readonly registrationMode = computed(() => this.resumen()?.registration_mode ?? null);
  readonly cargando = this.cargandoEstado.asReadonly();
  readonly falloCarga = this.falloEstado.asReadonly();

  constructor() {
    effect(() => {
      const id = this.eventId();
      if (!id) {
        this.resumen.set(null);
        this.falloEstado.set(false);
        return;
      }
      const cacheado = this.cache.get(id);
      if (cacheado) {
        this.resumen.set(cacheado);
        this.falloEstado.set(false);
        return;
      }
      this.resumen.set(null);
      void this.cargar(id);
    });
  }

  private idDesdeRuta(ruta: ActivatedRouteSnapshot): string | null {
    // `roles/:id` también declara un parámetro `id`: sin acotar por los segmentos de
    // la URL realmente emparejados por este nodo, `/admin/roles/r1` activaría por
    // error el ámbito de evento. Solo cuando el propio nodo ha emparejado un
    // segmento literal `events` (`events/:id`, `events/:eventId/…`) pertenece al
    // árbol de un evento.
    const enArbolDeEvento = ruta.url.some((segmento) => segmento.path === 'events');
    if (enArbolDeEvento) {
      const propio = ruta.paramMap.get('eventId') ?? ruta.paramMap.get('id');
      if (propio) {
        return propio;
      }
    }
    for (const hijo of ruta.children) {
      const encontrado = this.idDesdeRuta(hijo);
      if (encontrado) {
        return encontrado;
      }
    }
    return null;
  }

  private async cargar(id: string): Promise<void> {
    this.cargandoEstado.set(true);
    this.falloEstado.set(false);
    try {
      const evento = await firstValueFrom(
        this.http.get<EventoResumen>(this.api.url(`/events/${id}`)),
      );
      this.cache.set(id, evento);
      // La ruta pudo cambiar de evento mientras la petición estaba en vuelo: no
      // pintar un nombre que ya no corresponde al evento activo.
      if (this.eventId() === id) {
        this.resumen.set(evento);
      }
    } catch {
      if (this.eventId() === id) {
        this.falloEstado.set(true);
      }
    } finally {
      // Igual que en los bloques anteriores: la ruta pudo cambiar de evento mientras
      // la petición estaba en vuelo. Sin este guardado, la respuesta tardía del
      // evento anterior apagaría `cargando` mientras el nuevo evento activo todavía
      // está cargando el suyo.
      if (this.eventId() === id) {
        this.cargandoEstado.set(false);
      }
    }
  }
}
