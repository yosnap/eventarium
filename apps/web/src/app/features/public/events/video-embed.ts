/**
 * Resuelve cómo mostrar el vídeo de una sesión según `video_platform`.
 *
 * `youtube` y `vimeo` se embeben en un `iframe` a partir del identificador
 * extraído de la URL guardada. `twitch` también se embebe, pero su reproductor
 * exige declarar el dominio que lo aloja (`parent`); ese dominio se recibe como
 * parámetro (`ApiService.currentHost()`) en vez de asumirlo, porque en SSR no hay
 * `window` del que leerlo. Para `other` (o si no se puede extraer el
 * identificador) se ofrece un enlace directo: un `iframe` genérico podría
 * simplemente no cargar.
 */

export interface VideoEmbed {
  readonly kind: 'iframe' | 'link';
  readonly src: string;
}

function extraerIdDeYouTube(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname.endsWith('youtu.be')) {
      return u.pathname.slice(1) || null;
    }
    const v = u.searchParams.get('v');
    if (v) {
      return v;
    }
    const coincidencia = /\/embed\/([^/?]+)/.exec(u.pathname);
    return coincidencia ? coincidencia[1] : null;
  } catch {
    return null;
  }
}

function extraerIdDeVimeo(url: string): string | null {
  try {
    const u = new URL(url);
    const coincidencia = /\/(\d+)/.exec(u.pathname);
    return coincidencia ? coincidencia[1] : null;
  } catch {
    return null;
  }
}

function resolverEmbedDeTwitch(url: string, host: string): VideoEmbed | null {
  try {
    const u = new URL(url);
    if (u.hostname.endsWith('clips.twitch.tv')) {
      const clip = u.pathname.split('/').filter(Boolean).pop();
      return clip
        ? { kind: 'iframe', src: `https://clips.twitch.tv/embed?clip=${clip}&parent=${host}` }
        : null;
    }
    const segmentos = u.pathname.split('/').filter(Boolean);
    if (segmentos[0] === 'videos' && segmentos[1]) {
      return {
        kind: 'iframe',
        src: `https://player.twitch.tv/?video=${segmentos[1]}&parent=${host}`,
      };
    }
    if (segmentos[0]) {
      return {
        kind: 'iframe',
        src: `https://player.twitch.tv/?channel=${segmentos[0]}&parent=${host}`,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function resolveVideoEmbed(
  platform: string | null,
  url: string | null,
  host: string,
): VideoEmbed | null {
  if (!url) {
    return null;
  }
  if (platform === 'youtube') {
    const id = extraerIdDeYouTube(url);
    return id
      ? { kind: 'iframe', src: `https://www.youtube-nocookie.com/embed/${id}` }
      : { kind: 'link', src: url };
  }
  if (platform === 'vimeo') {
    const id = extraerIdDeVimeo(url);
    return id
      ? { kind: 'iframe', src: `https://player.vimeo.com/video/${id}` }
      : { kind: 'link', src: url };
  }
  if (platform === 'twitch') {
    return resolverEmbedDeTwitch(url, host) ?? { kind: 'link', src: url };
  }
  return { kind: 'link', src: url };
}
