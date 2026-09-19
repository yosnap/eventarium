/**
 * Tipos de imagen aceptados por el selector de fichero (`accept`) en los
 * campos que usan `app-media-picker`: logo de organización, identidad de
 * plataforma (logo/favicon), portada de evento, logo de patrocinador.
 *
 * Constantes por perfil, no un único valor para todo (hallazgo de red-team
 * del plan `260918-1944-biblioteca-de-medios`, fase 4): aunque hoy los 4
 * perfiles aceptan los mismos tipos, mantenerlos como constantes separadas
 * evita que ampliar lo que acepta un perfil (p. ej. SVG para logos)
 * arrastre sin querer a los demás.
 *
 * Ya no valida por bytes/tamaño en el cliente: desde que `MediaFields` sube
 * directo a la biblioteca (Fase 3 del mismo plan), esa validación real vive
 * en el servidor (`app/core/storage.py::validate_upload`) — duplicarla aquí
 * solo podía desincronizarse del límite real.
 */
const TIPOS_DE_IMAGEN_BASE = 'image/png,image/jpeg,image/webp';

/** Logo de organización, logo/favicon de plataforma, logo de patrocinador. */
export const LOGO_ACEPTADOS = TIPOS_DE_IMAGEN_BASE;
/** Portada de evento. */
export const PORTADA_ACEPTADOS = TIPOS_DE_IMAGEN_BASE;
