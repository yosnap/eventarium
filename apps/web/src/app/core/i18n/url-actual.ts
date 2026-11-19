import { inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter, map } from 'rxjs';

/**
 * URL actual del router como señal. Los componentes de la cabecera y el pie no se
 * vuelven a crear al navegar y son `OnPush`: sin esto mostrarían la URL de la
 * primera página. Se llama en un contexto de inyección.
 */
export function urlActual() {
  const router = inject(Router);
  return toSignal(
    router.events.pipe(
      filter((evento) => evento instanceof NavigationEnd),
      map((evento) => evento.urlAfterRedirects),
    ),
    { initialValue: router.url },
  );
}
