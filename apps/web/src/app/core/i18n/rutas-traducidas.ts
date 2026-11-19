import { IDIOMA_POR_DEFECTO, Idioma } from './idioma';

/**
 * Rutas públicas en cada idioma, por su ruta en español.
 *
 * Las claves son patrones: los segmentos con `:` son parámetros (identificador de la
 * organización, del evento, de una sesión…) y nunca se traducen; solo cambian los
 * segmentos fijos. Una ruta que no está aquí se llama igual en todos los idiomas.
 * Las rutas del router, los enlaces, el selector de idioma y el SEO salen de este
 * mapa, y la API tiene un espejo de las que enlaza (`app/core/locale.py`).
 */
const RUTAS_TRADUCIDAS: Readonly<Partial<Record<Idioma, Readonly<Record<string, string>>>>> = {
  'en-US': {
    acceder: 'login',
    registro: 'signup',
    'verificar-correo': 'verify-email',
    'crear-organizacion': 'create-organization',
    'recuperar-contrasena': 'forgot-password',
    'recuperar-contrasena/nueva': 'forgot-password/new',
    invitacion: 'invitation',
    'cuenta/confirmar-correo': 'account/confirm-email',
    'verificar-inscripcion': 'verify-registration',
    'confirmar-promocion': 'confirm-promotion',
    'cancelar-inscripcion': 'cancel-registration',
    'mi-entrada': 'my-ticket',
    eventos: 'events',
    'pago/retorno': 'payment/return',
    'pago/cancelado': 'payment/cancelled',
    'ponentes/:publicSlug': 'speakers/:publicSlug',
    'vista-previa/:eventId': 'preview/:eventId',
    'mis-eventos': 'my-events',
    'mis-eventos/ver': 'my-events/view',
    'legal/aviso-legal': 'legal/legal-notice',
    'legal/privacidad': 'legal/privacy',
    'legal/cookies': 'legal/cookies',
    'legal/condiciones-de-inscripcion': 'legal/registration-terms',
    ':org/:evento/sesiones/:sessionId': ':org/:evento/sessions/:sessionId',
    ':org/:evento/programa': ':org/:evento/schedule',
    ':org/:evento/patrocinadores/:sponsorId': ':org/:evento/sponsors/:sponsorId',
    ':org/:evento/politicas': ':org/:evento/policies',
    ':org/:evento/inscribirse': ':org/:evento/register',
  },
};

/** La ruta fija (patrón exacto del mapa) en `idioma`. */
export function rutaEn(idioma: Idioma, rutaEnEspanol: string): string {
  return RUTAS_TRADUCIDAS[idioma]?.[rutaEnEspanol] ?? rutaEnEspanol;
}

/** Lo que va detrás de `:org/:evento/` en `idioma` (`programa` → `schedule`). */
export function subrutaDeEvento(idioma: Idioma, subruta: string): string {
  return rutaEn(idioma, `:org/:evento/${subruta}`).split('/').slice(2).join('/');
}

/** Ruta de `serverRoutes` (admite `/**` al final) en `idioma`. */
export function rutaDeServidor(idioma: Idioma, ruta: string): string {
  if (!ruta.endsWith('/**')) {
    return rutaEn(idioma, ruta);
  }
  const base = ruta.slice(0, -3);
  const patron = Object.keys(RUTAS_TRADUCIDAS[idioma] ?? {}).find((clave) =>
    clave.startsWith(`${base}/`),
  );
  const traducida = patron
    ? rutaEn(idioma, patron).split('/').slice(0, base.split('/').length)
    : [base];
  return `${traducida.join('/')}/**`;
}

/** Segmentos fijos que más pesan primero: `pago/retorno` antes que `:org/:evento`. */
function patrones(mapa: Readonly<Record<string, string>>): [string[], string[]][] {
  return Object.entries(mapa)
    .map(([desde, hacia]): [string[], string[]] => [desde.split('/'), hacia.split('/')])
    .sort(
      ([a], [b]) =>
        b.filter((s) => !s.startsWith(':')).length - a.filter((s) => !s.startsWith(':')).length,
    );
}

function aplicar(segmentos: string[], mapa: Readonly<Record<string, string>>): string[] {
  for (const [desde, hacia] of patrones(mapa)) {
    const coincide =
      desde.length === segmentos.length &&
      desde.every((patron, i) => patron.startsWith(':') || patron === segmentos[i]);
    if (coincide) {
      return segmentos.map((segmento, i) => (desde[i].startsWith(':') ? segmento : hacia[i]));
    }
  }
  return segmentos;
}

function invertido(idioma: Idioma): Readonly<Record<string, string>> {
  return Object.fromEntries(
    Object.entries(RUTAS_TRADUCIDAS[idioma] ?? {}).map(([es, otro]) => [otro, es]),
  );
}

/**
 * La misma ruta (sin prefijo de idioma, con `?…`/`#…` si los lleva) pasada de un
 * idioma a otro: `/acme/iawic/programa` → `/acme/iawic/schedule`.
 */
export function traducirRuta(ruta: string, desde: Idioma, hacia: Idioma): string {
  if (desde === hacia) {
    return ruta;
  }
  const corte = ruta.search(/[?#]/);
  const camino = corte === -1 ? ruta : ruta.slice(0, corte);
  const resto = corte === -1 ? '' : ruta.slice(corte);
  const segmentos = camino.split('/').filter(Boolean);
  const enEspanol = desde === IDIOMA_POR_DEFECTO ? segmentos : aplicar(segmentos, invertido(desde));
  const destino =
    hacia === IDIOMA_POR_DEFECTO ? enEspanol : aplicar(enEspanol, RUTAS_TRADUCIDAS[hacia] ?? {});
  return `/${destino.join('/')}${resto}`;
}
