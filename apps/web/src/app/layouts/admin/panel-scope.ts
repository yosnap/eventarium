import { Injectable, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter, map, startWith } from 'rxjs/operators';

/**
 * En qué panel está el shell.
 *
 * El shell de administración lo comparten **dos** paneles con árboles de ruta
 * distintos —`/admin` para la plataforma y `/dashboard` para la organización—,
 * así que no puede saber por su propio componente qué navegación pintar: tiene
 * que mirar la URL. Vive en un servicio y no en el componente por la misma razón
 * que `EventScope`: la decisión se toma desde el router, y así las pruebas la
 * pueden fijar sin montar el árbol de rutas entero.
 */
@Injectable({ providedIn: 'root' })
export class PanelScope {
  private readonly router = inject(Router);

  /**
   * Se recalcula en cada navegación, no una sola vez: el shell no se recrea al
   * saltar de un panel a otro, así que una lectura única dejaría la navegación
   * mostrando el grupo del panel anterior.
   */
  private readonly navegacion = toSignal(
    this.router.events.pipe(
      filter((evento) => evento instanceof NavigationEnd),
      startWith(null),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );

  /** `true` en el panel de plataforma (`/admin`), `false` en el de organización. */
  readonly esPlataforma = computed(() => this.navegacion().startsWith('/admin'));
}
