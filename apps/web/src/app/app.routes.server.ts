import { RenderMode, ServerRoute } from '@angular/ssr';

/**
 * Modos de renderizado.
 *
 * Las rutas públicas se renderizan en el servidor **por petición**, no prerenderizadas:
 * el contenido depende del host, y cada organización tiene su propia marca. El panel es
 * solo cliente: necesita la cookie de sesión, que el servidor no debe manejar.
 */
export const serverRoutes: ServerRoute[] = [
  { path: 'admin', renderMode: RenderMode.Client },
  { path: 'admin/**', renderMode: RenderMode.Client },
  { path: '**', renderMode: RenderMode.Server },
];
