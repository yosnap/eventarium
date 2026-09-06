/**
 * Configuración de producción.
 *
 * En el navegador la API es relativa: web y API comparten host tras Caddy, así que la
 * cookie de sesión es first-party y no hay CORS. En SSR el servidor Node necesita una
 * URL absoluta porque llama a la API por la red interna.
 */

/**
 * Lee una variable de entorno solo cuando existe `process`.
 *
 * El mismo fichero se compila para el navegador, donde `process` no existe: leerlo
 * directamente rompería el bundle.
 */
function variableDeEntorno(nombre: string): string | undefined {
  const proceso = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  return proceso?.env?.[nombre];
}

export const environment = {
  production: true,
  apiPath: '/api/v1',
  serverApiBaseUrl: variableDeEntorno('API_INTERNAL_URL') ?? 'http://api:8000',
} as const;
