import { IDIOMAS, Idioma, IDIOMA_POR_DEFECTO, esIdioma, urlEnIdioma } from '../i18n/idioma';

/** Lo que una página sabe de sí misma para decidir cómo se indexa en cada idioma. */
export interface EntradaDeIndexacion {
  /** Ruta de la página sin prefijo de idioma (`/acme/iawic`). */
  readonly ruta: string;
  /** Idioma en el que se está mostrando. */
  readonly activo: Idioma;
  /**
   * Si la página muestra contenido escrito por el organizador (evento, sesión,
   * ponente…). Ese contenido solo cuenta como disponible en un idioma cuando su
   * traducción está al día; la interfaz de la plataforma lo está siempre.
   */
  readonly contenidoDelOrganizador: boolean;
  /** Idioma en que escribió el organizador. Por defecto, el de la plataforma. */
  readonly idiomaOrigen?: Idioma;
  /**
   * Idiomas con la traducción del contenido al día, según la API. Sin el dato,
   * solo cuenta el idioma de origen.
   */
  readonly idiomasAlDia?: readonly Idioma[];
  /** Idiomas que ofrece la plataforma (`/admin/idiomas`). Sin el dato, todos. */
  readonly idiomasActivos?: readonly Idioma[];
}

export interface DecisionDeIndexacion {
  /** Ruta canónica, ya con el prefijo del idioma que corresponda. */
  readonly canonica: string;
  /** Versiones por idioma (`hreflang`), solo si esta página es la canónica. */
  readonly alternativas: readonly {
    readonly idioma: Idioma | 'x-default';
    readonly ruta: string;
  }[];
  readonly ogLocale: string;
  readonly ogLocaleAlternativos: readonly string[];
}

const comoOgLocale = (idioma: Idioma) => idioma.replace('-', '_');

/**
 * Única decisión de indexación por idioma de la web pública.
 *
 * - Una página solo se ofrece a los buscadores en los idiomas en que está al día.
 * - Una versión que no está al día no se marca `noindex`: lleva `canonical` a la
 *   versión original y no anuncia alternativas. Las dos señales juntas se
 *   contradicen y los buscadores las tratan mal.
 * - `x-default` y la URL sin prefijo siguen al idioma de origen, así que un evento
 *   escrito en inglés también funciona.
 */
export function decidirIndexacion(entrada: EntradaDeIndexacion): DecisionDeIndexacion {
  const origen = entrada.idiomaOrigen ?? IDIOMA_POR_DEFECTO;
  const activos = entrada.idiomasActivos ?? IDIOMAS;
  const disponibles = (
    entrada.contenidoDelOrganizador
      ? IDIOMAS.filter((idioma) => idioma === origen || entrada.idiomasAlDia?.includes(idioma))
      : IDIOMAS
  ).filter((idioma) => idioma === origen || activos.includes(idioma));
  const ogLocale = comoOgLocale(entrada.activo);

  if (!disponibles.includes(entrada.activo)) {
    return {
      canonica: urlEnIdioma(entrada.ruta, origen),
      alternativas: [],
      ogLocale,
      ogLocaleAlternativos: [],
    };
  }
  return {
    canonica: urlEnIdioma(entrada.ruta, entrada.activo),
    alternativas:
      disponibles.length > 1
        ? [
            ...disponibles.map((idioma) => ({ idioma, ruta: urlEnIdioma(entrada.ruta, idioma) })),
            { idioma: 'x-default' as const, ruta: urlEnIdioma(entrada.ruta, origen) },
          ]
        : [],
    ogLocale,
    ogLocaleAlternativos: disponibles
      .filter((idioma) => idioma !== entrada.activo)
      .map(comoOgLocale),
  };
}

/** Campos de idioma que añade la API a las respuestas con contenido del organizador. */
export interface IdiomasDeLaRespuesta {
  readonly source_locale?: string;
  readonly up_to_date_locales?: readonly string[];
  /** Idioma en que llega el contenido: el de la página o, sin traducir, el original. */
  readonly served_locale?: string;
  /** La IA va a traducir lo pendiente: la página espera con un esqueleto. */
  readonly translating?: boolean;
  /** Campos principales que se están traduciendo: esqueleto solo en esos bloques. */
  readonly translating_fields?: readonly string[];
}

/**
 * `idiomaOrigen` e `idiomasAlDia` para `SeoMetaService.set` a partir de la
 * respuesta de la API. Los valores que la web no conoce se descartan.
 */
export function idiomasDeLaRespuesta(
  respuesta: IdiomasDeLaRespuesta,
): Pick<EntradaDeIndexacion, 'idiomaOrigen' | 'idiomasAlDia'> {
  const origen = respuesta.source_locale;
  return {
    idiomaOrigen: esIdioma(origen) ? origen : undefined,
    idiomasAlDia: (respuesta.up_to_date_locales ?? []).filter(esIdioma),
  };
}
