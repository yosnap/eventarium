import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

/**
 * Qué hace falta para ver una pantalla del panel. Una sola fuente para el menú
 * (`admin-nav.ts`) y para el guard de la ruta, para que nunca diverjan: el
 * backend sigue siendo la autoridad, esto evita enseñar enlaces y pantallas
 * que solo devolverían un 403.
 *
 * - `permiso`: uno concreto.
 * - `cualquiera`: basta uno de la lista.
 * - `rol`: un rol de la organización (la IA solo la toca el propietario).
 * - `gestion`: algún permiso más allá de ver la organización; quien solo tiene
 *   `organizations:read` (un ponente) no gestiona nada.
 * - `ninguno`: cualquier miembro (su cuenta y su ficha).
 */
export type RequisitoDePanel =
  | { readonly permiso: string }
  | { readonly cualquiera: readonly string[] }
  | { readonly rol: string }
  | 'gestion'
  | 'ninguno';

/** El único permiso que tiene un rol que no gestiona nada (ponente). */
const PERMISO_DE_SOLO_VER = 'organizations:read';

const p = (permiso: string): RequisitoDePanel => ({ permiso });

/**
 * Requisito de cada ruta de `/dashboard`, sacado del permiso que exige el
 * endpoint con el que carga cada pantalla. Organización, identidad visual y
 * políticas se pueden **leer** con `organizations:read`, pero se piden de
 * escritura a propósito: un ponente tiene ese permiso y no debe ver más que su
 * ficha (decisión del dueño, 19-oct). La IA la gestiona solo el propietario
 * (`OrgOwnerDep`), por rol.
 */
export const REQUISITOS_DEL_PANEL = {
  '': 'gestion',
  organization: p('organizations:write'),
  branding: p('branding:write'),
  politicas: p('organizations:write'),
  roles: p('roles:read'),
  'roles/:id': p('roles:read'),
  members: p('members:read'),
  'members/nuevo': p('members:write'),
  events: p('events:read'),
  'events/nuevo': p('events:write'),
  // El voluntariado (`tickets:write`, sin `events:read`) entra al check-in de
  // un evento por enlace directo: no se le cierra el evento entero.
  'events/:eventId': { cualquiera: ['events:read', 'tickets:write'] },
  'events/:eventId/editar': p('events:write'),
  'events/:eventId/registrations/:registrationId': p('registrations:read'),
  // Escanear y buscar entradas (`/tickets/scan*`, `/tickets/search`) es lo que
  // hace la pantalla, y eso exige `tickets:write`.
  'events/:eventId/check-in': p('tickets:write'),
  'events/:eventId/payments': p('payments:read'),
  'events/:eventId/contabilidad': p('accounting:read'),
  'events/:eventId/agenda': p('events:read'),
  'events/:eventId/diseno': p('events:read'),
  'events/:eventId/entradas': p('payments:read'),
  'events/:eventId/descuentos': p('payments:read'),
  'events/:eventId/patrocinadores': p('sponsors:read'),
  'events/:eventId/ponentes': p('events:read'),
  'events/:eventId/politicas': p('events:read'),
  'events/:eventId/inscripciones': p('registrations:read'),
  'sponsor-tiers': p('sponsors:read'),
  // Gestionarlos: lo mismo que crear sesiones. Leerlos solo hace falta en el
  // formulario de sesión, que ya exige `events:write`.
  'session-types': p('events:write'),
  stripe: p('payments:read'),
  ia: { rol: 'owner' },
  account: 'ninguno',
  // Ayuda de la traducción automática: la enlazan los avisos del panel.
  'ayuda/traduccion': 'gestion',
  mcp: p('mcp:connect'),
} as const satisfies Record<string, RequisitoDePanel>;

export type RutaDelPanel = keyof typeof REQUISITOS_DEL_PANEL;

/** Adónde va quien entra en una pantalla del panel que no le corresponde. */
export const RUTA_SIN_PERMISO = ['/dashboard', 'account'] as const;

export function cumpleRequisito(
  requisito: RequisitoDePanel,
  permisos: readonly string[],
  roles: readonly string[],
): boolean {
  if (requisito === 'ninguno') return true;
  if (requisito === 'gestion') return permisos.some((p) => p !== PERMISO_DE_SOLO_VER);
  if ('permiso' in requisito) return permisos.includes(requisito.permiso);
  if ('cualquiera' in requisito) return requisito.cualquiera.some((p) => permisos.includes(p));
  return roles.includes(requisito.rol);
}

/**
 * Guard de una ruta del panel. Espera a tener los permisos (tras el login el
 * usuario en memoria no los trae) y, si no se cumple el requisito, lleva a la
 * ficha propia. Si `/users/me` falla, deja pasar: es el backend quien decide,
 * y echar a alguien por un fallo de red sería peor que un 403 explicado.
 */
export function requierePermiso(requisito: RequisitoDePanel): CanActivateFn {
  return async () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    try {
      const usuario = await auth.asegurarUsuarioCompleto();
      return cumpleRequisito(requisito, usuario.permissions ?? [], usuario.roles ?? [])
        ? true
        : router.createUrlTree([...RUTA_SIN_PERMISO]);
    } catch {
      return true;
    }
  };
}

/** Guard de una ruta del panel, por su clave en `REQUISITOS_DEL_PANEL`. */
export function guardDe(ruta: RutaDelPanel): CanActivateFn {
  return requierePermiso(REQUISITOS_DEL_PANEL[ruta]);
}
