import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { ApiService } from '../api/api.service';
import { AuthService } from './auth.service';

/**
 * Protege el panel de la plataforma (`/admin` y sus secciones). El backend ya
 * exige `is_superadmin` en cada endpoint (`require_superadmin`); este guard cierra
 * el hueco de que, hasta ahora, el panel solo estaba oculto por un enlace
 * condicional en `admin-shell.ts` y era alcanzable por URL directa a cualquier
 * autenticado. Las herramienta de desarrollo (`/dashboard/estilo`) **no** lleva
 * este guard: sigue accesible a cualquier persona autenticada (pregunta abierta 3
 * de `plan.md`).
 */
export const superadminGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const api = inject(ApiService);
  const router = inject(Router);

  // El panel es solo cliente: en SSR no hay sesión que consultar. `authGuard`, en el
  // padre, ya deniega aquí; este guard solo necesita no romper esa ruta.
  if (api.isServer) {
    return false;
  }

  let usuario = auth.currentUser();
  if (!usuario) {
    try {
      usuario = await auth.loadCurrentUser();
    } catch {
      return router.createUrlTree(['/acceder']);
    }
  }

  // Quien no administra la instalación vuelve a **su** panel, que es `/dashboard`.
  // Redirigir a `/admin` lo dejaría rebotando contra este mismo guard.
  return usuario.is_superadmin ? true : router.createUrlTree(['/dashboard']);
};
