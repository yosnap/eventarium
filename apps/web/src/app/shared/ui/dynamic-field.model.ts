/** Espejo de `FIELD_TYPES` en `app/modules/roles/models.py`. */
export const FIELD_TYPES = [
  'text',
  'textarea',
  'url',
  'email',
  'phone',
  'date',
  'select',
  'boolean',
] as const;

export type FieldType = (typeof FIELD_TYPES)[number];

/** Campo de perfil de un rol, tal y como lo sirve la API (`ProfileFieldResponse`). */
export interface ProfileField {
  readonly key: string;
  readonly label: string;
  readonly field_type: string;
  readonly options: { readonly choices?: readonly string[] } | null;
  readonly is_required: boolean;
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const URL_RE = /^https?:\/\/\S+$/;
const PHONE_RE = /^[+0-9 ().-]{6,30}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Valida un valor de `profile_data` contra la definición de su campo.
 *
 * Espejo en el cliente de `app/shared/dynamic_fields.py`, para dar el error antes de
 * enviar — la API vuelve a validar siempre, esto no la sustituye.
 */
export function validateDynamicFieldValue(
  field: ProfileField,
  valor: string | boolean,
): string | null {
  const vacio = valor === '' || valor === null || valor === undefined;
  if (field.is_required && vacio) {
    return `«${field.label}» es obligatorio.`;
  }
  if (vacio) {
    return null;
  }

  switch (field.field_type) {
    case 'email':
      return typeof valor === 'string' && EMAIL_RE.test(valor.trim())
        ? null
        : `«${field.label}» debe ser un correo electrónico válido.`;
    case 'url':
      return typeof valor === 'string' && URL_RE.test(valor.trim())
        ? null
        : `«${field.label}» debe ser una URL que empiece por http(s).`;
    case 'phone':
      return typeof valor === 'string' && PHONE_RE.test(valor.trim())
        ? null
        : `«${field.label}» debe ser un teléfono válido.`;
    case 'date':
      return typeof valor === 'string' && DATE_RE.test(valor) && !Number.isNaN(Date.parse(valor))
        ? null
        : `«${field.label}» debe ser una fecha válida (AAAA-MM-DD).`;
    case 'select': {
      const opciones = field.options?.choices ?? [];
      return opciones.includes(valor as string)
        ? null
        : `«${field.label}» debe ser una de las opciones disponibles.`;
    }
    case 'boolean':
      return typeof valor === 'boolean' ? null : `«${field.label}» debe ser verdadero o falso.`;
    default:
      return null;
  }
}
