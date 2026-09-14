import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { ApiService } from '../api/api.service';
import { AuthService } from './auth.service';

/**
 * Protege `/acceder` en el sentido contrario a `authGuard`: si ya hay una sesión
 * válida, no tiene sentido ver el formulario.
 *
 * Sin esto, un intento de login fallido con una cuenta distinta a la de la sesión
 * activa (credenciales incorrectas para esa cuenta, por ejemplo) no avisa de nada:
 * la sesión previa sigue viva y basta con navegar a una ruta protegida para entrar
 * con ella, sin que la persona sepa con qué cuenta ha acabado. Redirigir aquí lo
 * deja explícito en vez de dejarlo para que lo descubra por sorpresa en otra
 * pantalla.
 *
 * Mismo intento de renovar con la cookie que `authGuard`: sin token en memoria
 * (recarga, pestaña nueva) no basta con mirar `isAuthenticated()` para saber si
 * hay sesión.
 */
export const guestGuard: CanActivateFn = async (ruta) => {
  const auth = inject(AuthService);
  const api = inject(ApiService);
  const router = inject(Router);

  // En SSR no hay cookie que consultar: se renderiza el formulario tal cual.
  if (api.isServer) {
    return true;
  }

  const yaAutenticado = auth.isAuthenticated() || (await auth.refresh());
  if (!yaAutenticado) {
    return true;
  }

  // Mismo destino por defecto que tras un login (`login-page.ts`): `/dashboard`,
  // salvo que la navegación llevara ya un `redirigir` explícito (p. ej. un guard
  // que rebotó aquí antes de que la sesión se hubiera renovado).
  const destino = ruta.queryParamMap.get('redirigir') ?? '/dashboard';
  return router.createUrlTree([destino]);
};
