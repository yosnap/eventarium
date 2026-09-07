import { describe, expect, it } from 'vitest';

import { ProfileField, validateDynamicFieldValue } from './dynamic-field.model';

function campo(sobrescribir: Partial<ProfileField> = {}): ProfileField {
  return {
    key: 'campo',
    label: 'Campo',
    field_type: 'text',
    options: null,
    is_required: false,
    ...sobrescribir,
  };
}

describe('validateDynamicFieldValue', () => {
  it('exige un valor cuando el campo es obligatorio', () => {
    expect(validateDynamicFieldValue(campo({ is_required: true }), '')).toContain('obligatorio');
  });

  it('un campo opcional vacío no da error', () => {
    expect(validateDynamicFieldValue(campo(), '')).toBeNull();
  });

  it('valida el formato de correo electrónico', () => {
    const definicion = campo({ field_type: 'email' });
    expect(validateDynamicFieldValue(definicion, 'no-es-un-correo')).toContain('correo');
    expect(validateDynamicFieldValue(definicion, 'persona@example.com')).toBeNull();
  });

  it('valida que la URL empiece por http(s)', () => {
    const definicion = campo({ field_type: 'url' });
    expect(validateDynamicFieldValue(definicion, 'www.example.com')).toContain('URL');
    expect(validateDynamicFieldValue(definicion, 'https://example.com')).toBeNull();
  });

  it('valida el formato de teléfono', () => {
    const definicion = campo({ field_type: 'phone' });
    expect(validateDynamicFieldValue(definicion, 'abc')).toContain('teléfono');
    expect(validateDynamicFieldValue(definicion, '+34 600 123 456')).toBeNull();
  });

  it('valida que la fecha sea ISO y real', () => {
    const definicion = campo({ field_type: 'date' });
    expect(validateDynamicFieldValue(definicion, '31/12/2026')).toContain('fecha');
    expect(validateDynamicFieldValue(definicion, '2026-13-40')).toContain('fecha');
    expect(validateDynamicFieldValue(definicion, '2026-12-31')).toBeNull();
  });

  it('valida que el valor de un selector esté entre las opciones', () => {
    const definicion = campo({ field_type: 'select', options: { choices: ['S', 'M', 'L'] } });
    expect(validateDynamicFieldValue(definicion, 'XL')).toContain('opciones');
    expect(validateDynamicFieldValue(definicion, 'M')).toBeNull();
  });

  it('exige un booleano real para el tipo booleano', () => {
    const definicion = campo({ field_type: 'boolean' });
    expect(validateDynamicFieldValue(definicion, 'true')).toContain('verdadero');
    expect(validateDynamicFieldValue(definicion, true)).toBeNull();
  });
});
