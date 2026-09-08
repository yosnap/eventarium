import { RenderMode, ServerRoute } from '@angular/ssr';

/**
 * Modos de renderizado.
 *
 * Las rutas públicas se renderizan en el servidor **por petición**, no prerenderizadas:
 * el contenido depende del host, y cada organización tiene su propia marca. El panel es
 * solo cliente: necesita la cookie de sesión, que el servidor no debe manejar.
 */
/**
 * Páginas que consumen un token de un solo uso en su propio constructor, sin
 * esperar interacción de la persona (verificación de correo, promoción de
 * lista de espera, autocancelación…). En SSR por petición, el servidor
 * ejecuta el constructor para prerenderizar y el cliente lo vuelve a
 * ejecutar al hidratar — el token ya estaría consumido y la hidratación
 * mostraría siempre "enlace caducado" aunque la acción del servidor haya
 * funcionado. Solo cliente evita la doble ejecución.
 */
const PAGINAS_DE_TOKEN_DE_UN_SOLO_USO = [
  'verificar-correo',
  'recuperar-contrasena/nueva',
  'cuenta/confirmar-correo',
  'verificar-inscripcion',
  'confirmar-promocion',
  'cancelar-inscripcion',
];

export const serverRoutes: ServerRoute[] = [
  { path: 'admin', renderMode: RenderMode.Client },
  { path: 'admin/**', renderMode: RenderMode.Client },
  ...PAGINAS_DE_TOKEN_DE_UN_SOLO_USO.map(
    (path): ServerRoute => ({ path, renderMode: RenderMode.Client }),
  ),
  { path: '**', renderMode: RenderMode.Server },
];
