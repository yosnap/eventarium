import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';

import { ApiService } from '../api/api.service';
import { esPersonalDePlataforma, AuthService, UsuarioAutenticado } from './auth.service';

/**
 * Resuelve quién entra, o a dónde rebotarlo si no hay sesión utilizable.
 *
 * Lo comparten los guards del panel de plataforma (`personalPlataformaGuard`
 * y `superadminGuard`): el camino de «sin token en memoria → refrescar con la
 * cookie → cargar el usuario» es delicado y no puede existir en dos copias que
 * se desincronicen.
 *
 * Hay que llamarlo **antes del primer `await`** del guard, mientras el
 * contexto de inyección sigue activo: usa `inject()`.
 */
export async function usuarioDelPanelDePlataforma(): Promise<UsuarioAutenticado | UrlTree | false> {
  const auth = inject(AuthService);
  const api = inject(ApiService);
  const router = inject(Router);

  // El panel es solo cliente: en SSR no hay sesión que consultar. `authGuard`,
  // en el padre, ya deniega aquí; esto solo necesita no romper esa ruta.
  if (api.isServer) {
    return false;
  }

  const usuario = auth.currentUser();
  if (usuario) {
    return usuario;
  }
  // Sin token en memoria (recarga de página, pestaña nueva, URL directa a
  // `/admin` sin pasar antes por `/dashboard`) hay que intentar renovar con la
  // cookie antes de rendirse, igual que `authGuard`: sin este paso, entrar
  // directamente a `/admin` con una sesión válida rebotaba siempre a
  // `/acceder`, porque `loadCurrentUser()` fallaba sin `Authorization` antes
  // de que nada intentara refrescar el token.
  if (!(await auth.refresh())) {
    return router.createUrlTree(['/acceder']);
  }
  try {
    return await auth.loadCurrentUser();
  } catch {
    return router.createUrlTree(['/acceder']);
  }
}

/**
 * Protege el panel de la plataforma (`/admin` y sus secciones, catálogo de
 * componentes incluido). El backend ya comprueba los privilegios en cada
 * endpoint (`require_superadmin` para escritura, `require_platform_staff`
 * para lectura); este guard cierra el hueco de que, hasta ahora, el panel
 * solo estaba oculto por un enlace condicional en `admin-shell.ts` y era
 * alcanzable por URL directa a cualquier autenticado.
 *
 * Entra el **personal de plataforma** —superadmin, o el rol aditivo
 * `soporte` (fase 3 del plan de cookies: la pantalla de analítica externa
 * es de lectura también para soporte)—. Las páginas de escritura siguen
 * filtradas por `soloSuperadmin` en el nav y por 403 del backend.
 */
export const personalPlataformaGuard: CanActivateFn = async () => {
  const router = inject(Router);
  const usuario = await usuarioDelPanelDePlataforma();
  if (typeof usuario === 'boolean' || usuario instanceof UrlTree) {
    return usuario;
  }

  // Quien no es personal de plataforma vuelve a **su** panel, que es
  // `/dashboard`. Redirigir a `/admin` lo dejaría rebotando contra este
  // mismo guard.
  return esPersonalDePlataforma(usuario) ? true : router.createUrlTree(['/dashboard']);
};
