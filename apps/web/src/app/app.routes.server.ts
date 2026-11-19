import { RenderMode, ServerRoute } from '@angular/ssr';

import { IDIOMAS, PREFIJO_DE_IDIOMA } from './core/i18n/idioma';
import { rutaDeServidor } from './core/i18n/rutas-traducidas';

/**
 * Modos de renderizado.
 *
 * Las rutas públicas se renderizan en el servidor **por petición**, no prerenderizadas:
 * el contenido depende del host, y cada organización tiene su propia marca. El panel es
 * solo cliente: necesita la cookie de sesión, que el servidor no debe manejar.
 */
/**
 * Páginas que consumen un token de un solo uso en su propio constructor, sin
 * esperar interacción de la persona (verificación de correo, recuperación de
 * contraseña…). En SSR por petición, el servidor ejecuta el constructor para
 * prerenderizar y el cliente lo vuelve a ejecutar al hidratar — el token ya
 * estaría consumido y la hidratación mostraría siempre "enlace caducado"
 * aunque la acción del servidor haya funcionado. Solo cliente evita la doble
 * ejecución.
 *
 * Las tres páginas de inscripción (verificar, confirmar promoción de la lista
 * de espera y autocancelar) ya no están aquí: se renderizan en el servidor
 * para llevar su título en el HTML y solo consumen el token en el navegador
 * (`isPlatformBrowser` en su constructor).
 */
const PAGINAS_DE_TOKEN_DE_UN_SOLO_USO = [
  'verificar-correo',
  'recuperar-contrasena/nueva',
  'cuenta/confirmar-correo',
  // El enlace de «Mis eventos» es de un solo uso: renderizado en servidor, el
  // servidor lo gastaba y el navegador mostraba «enlace caducado».
  'mis-eventos/ver',
];

/**
 * Páginas públicas que se pintan solo en el navegador: necesitan la cookie de sesión
 * o consumen un token de un solo uso. Existen en la raíz y bajo el prefijo de cada
 * idioma, y en todos los casos tienen que ser solo de cliente: si una se renderizara
 * en el servidor bajo `/en/`, el servidor gastaría el token del enlace.
 */
export const PAGINAS_PUBLICAS_SOLO_DE_CLIENTE = [
  'acceder',
  // La vista previa necesita la sesión del equipo, que el servidor no tiene.
  'vista-previa/**',
  // Con la sesión iniciada lista sin pedir el correo; la sesión es la cookie
  // que el servidor no maneja.
  'mis-eventos',
  ...PAGINAS_DE_TOKEN_DE_UN_SOLO_USO,
];

/** Idiomas con prefijo de URL (todos menos el de por defecto). */
const IDIOMAS_CON_PREFIJO = IDIOMAS.filter((idioma) => PREFIJO_DE_IDIOMA[idioma] !== '');

const soloCliente = (path: string): ServerRoute => ({ path, renderMode: RenderMode.Client });

export const serverRoutes: ServerRoute[] = [
  ...PAGINAS_PUBLICAS_SOLO_DE_CLIENTE.flatMap((path) => [
    soloCliente(path),
    ...IDIOMAS_CON_PREFIJO.map((idioma) =>
      soloCliente(`${PREFIJO_DE_IDIOMA[idioma]}/${rutaDeServidor(idioma, path)}`),
    ),
  ]),
  // Los dos paneles (organización y plataforma) son solo cliente: necesitan la
  // cookie de sesión, que el servidor no debe manejar. Si se olvidara cualquiera
  // de estos, `authGuard` denegaría en SSR y el panel no cargaría.
  soloCliente('espacio-de-trabajo'),
  // Necesita la sesión, que el servidor no maneja.
  soloCliente('oauth/consentimiento'),
  soloCliente('admin'),
  soloCliente('admin/**'),
  soloCliente('dashboard'),
  soloCliente('dashboard/**'),
  { path: '**', renderMode: RenderMode.Server },
];
