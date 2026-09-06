import {
  AngularNodeAppEngine,
  createNodeRequestHandler,
  isMainModule,
  writeResponseToNodeResponse,
} from '@angular/ssr/node';
import express from 'express';
import { join } from 'node:path';

const browserDistFolder = join(import.meta.dirname, '../browser');

const app = express();

/**
 * Cabeceras de proxy en las que se confía.
 *
 * Hay que declararlas de forma explícita: Angular borra cualquier `x-forwarded-*` que
 * no esté en esta lista y, al hacerlo, degrada el renderizado a cliente **sin fallar**.
 * El valor por defecto no incluye `x-forwarded-for`, que Caddy envía siempre, así que
 * omitir esto rompería el SSR de forma silenciosa.
 */
const CABECERAS_DE_PROXY = [
  'x-forwarded-host',
  'x-forwarded-proto',
  'x-forwarded-for',
  'x-forwarded-port',
];

/**
 * Hosts permitidos.
 *
 * Angular valida `Host` y `X-Forwarded-Host` contra esta lista para evitar SSRF. En una
 * plataforma multi-organización los dominios son datos, no configuración de compilación:
 * dar de alta un organizador no puede exigir reconstruir la aplicación. Por eso la lista
 * se lee en tiempo de ejecución de `NG_ALLOWED_HOSTS` (separada por comas).
 *
 * Si no se define, se acepta cualquier host porque la validación ya ocurre dos veces
 * antes: Caddy solo enruta los dominios que tiene configurados, y la API resuelve la
 * organización por coincidencia exacta contra `organization_domains` y responde 404 si
 * no la encuentra. En un despliegue sin proxy delante, define la variable.
 */
function hostsPermitidos(): string[] {
  const valor = process.env['NG_ALLOWED_HOSTS'];
  const lista = (valor ?? '')
    .split(',')
    .map((host) => host.trim())
    .filter(Boolean);
  return lista.length > 0 ? lista : ['*'];
}

const angularApp = new AngularNodeAppEngine({
  allowedHosts: hostsPermitidos(),
  trustProxyHeaders: CABECERAS_DE_PROXY,
});

/** Ficheros estáticos del build del navegador. */
app.use(
  express.static(browserDistFolder, {
    maxAge: '1y',
    index: false,
    redirect: false,
  }),
);

/** El resto lo renderiza Angular. */
app.use((req, res, next) => {
  angularApp
    .handle(req)
    .then((response) => (response ? writeResponseToNodeResponse(response, res) : next()))
    .catch(next);
});

if (isMainModule(import.meta.url) || process.env['pm_id']) {
  const port = process.env['PORT'] || 4000;
  app.listen(port, (error) => {
    if (error) {
      throw error;
    }
    console.log(`Servidor SSR escuchando en http://localhost:${port}`);
  });
}

/** Handler que usan el CLI de Angular y el dev-server. */
export const reqHandler = createNodeRequestHandler(app);
