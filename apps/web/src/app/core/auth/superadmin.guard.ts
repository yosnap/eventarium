import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { ApiService } from '../api/api.service';
import { AuthService } from './auth.service';

/**
 * Protege las rutas que edita el equipo de plataforma: `/admin/superadmin` y
 * `/admin/superadmin/plantillas`. El backend ya exige `is_superadmin` en cada
 * endpoint (`require_superadmin`); este guard cierra el hueco de que, hasta ahora,
 * `/admin/superadmin` solo estaba oculta por un enlace condicional en `admin-shell.ts`
 * y alcanzable por URL directa a cualquier autenticado. `/admin/estilo` no lleva este
 * guard: sigue accesible a cualquier persona autenticada (pregunta abierta 3 de
 * `plan.md`).
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
      return router.createUrlTree(['/admin/login']);
    }
  }

  return usuario.is_superadmin ? true : router.createUrlTree(['/admin']);
};
