/** Configuración de desarrollo: la API local en el puerto 8000, tras Caddy en el 8080. */
export const environment = {
  production: false,
  apiPath: '/api/v1',
  serverApiBaseUrl: 'http://localhost:8000',
  // Turnstile está desactivado en desarrollo (ver TURNSTILE_ENABLED en la API): el
  // widget no se renderiza y se envía un token vacío, que el backend ignora.
  turnstileEnabled: false,
  turnstileSiteKey: '',
} as const;
