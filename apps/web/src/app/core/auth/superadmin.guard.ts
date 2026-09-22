import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';

import { esPersonalDePlataforma } from './auth.service';
import { usuarioDelPanelDePlataforma } from './personal-plataforma.guard';

/**
 * Pantallas de `/admin` que **solo** puede abrir un superadmin, no el rol
 * aditivo `soporte`: hoy, la configuración de IA de la plataforma (donde se
 * guarda una credencial de proveedor) y los interruptores de servicio.
 *
 * No es la barrera de autorización —el backend responde 403 a quien no sea
 * superadmin en esos endpoints (`require_superadmin`)—: evita llevar a
 * `soporte` a una pantalla que solo le daría errores, igual que
 * `soloSuperadmin` ya hace con su enlace del menú.
 */
export const superadminGuard: CanActivateFn = async () => {
  const router = inject(Router);
  const usuario = await usuarioDelPanelDePlataforma();
  if (typeof usuario === 'boolean' || usuario instanceof UrlTree) {
    return usuario;
  }

  if (usuario.is_superadmin) {
    return true;
  }
  // Quien es personal de plataforma pero no superadmin se queda en la portada
  // del panel de plataforma, que sí puede ver; quien ni siquiera lo es vuelve
  // a **su** panel, igual que decide `personalPlataformaGuard`.
  return router.createUrlTree([esPersonalDePlataforma(usuario) ? '/admin' : '/dashboard']);
};
