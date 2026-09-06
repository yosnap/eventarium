/** Configuración de desarrollo: la API local en el puerto 8000, tras Caddy en el 8080. */
export const environment = {
  production: false,
  apiPath: '/api/v1',
  serverApiBaseUrl: 'http://localhost:8000',
} as const;
