/**
 * Restricciones de subida de imágenes compartidas por los formularios que
 * suben una portada de evento o un logotipo de patrocinador: mismos tipos y
 * mismo límite de tamaño que valida `apps/api/app/core/storage.py`
 * (`ALLOWED_IMAGE_MIMES`, 5 MB). Antes duplicadas en `event-form.ts` y
 * `event-sponsors.ts` — un cambio de límite exigía tocar los dos a la vez.
 */
export const IMAGEN_MIMES_PERMITIDOS = new Set(['image/png', 'image/jpeg', 'image/webp']);
export const IMAGEN_TAMANO_MAXIMO = 5 * 1024 * 1024;
