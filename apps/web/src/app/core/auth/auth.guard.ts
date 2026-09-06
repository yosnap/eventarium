import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { ApiService } from '../api/api.service';
import { AuthService } from './auth.service';

/**
 * Protege las rutas del panel.
 *
 * Si no hay token en memoria (recarga de página, pestaña nueva) se intenta renovar con
 * la cookie antes de rendirse: así una recarga no expulsa a quien sí tiene sesión.
 */
export const authGuard: CanActivateFn = async (_ruta, estado) => {
  const auth = inject(AuthService);
  const api = inject(ApiService);
  const router = inject(Router);

  // El panel es solo cliente: en SSR no hay cookie que consultar.
  if (api.isServer) {
    return false;
  }

  if (auth.isAuthenticated()) {
    return true;
  }

  if (await auth.refresh()) {
    return true;
  }

  return router.createUrlTree(['/admin/login'], {
    queryParams: { redirigir: estado.url },
  });
};
