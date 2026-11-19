import { describe, expect, it } from 'vitest';

import { opcionesDePregunta, type RegistrationQuestion } from './registrations.service';

const pregunta: RegistrationQuestion = {
  id: 'p1',
  type: 'single_choice',
  label: '¿Talla?',
  required: false,
  options: ['Pequeña', 'Grande'],
  sort_order: 0,
};

describe('opcionesDePregunta', () => {
  it('muestra la etiqueta traducida y conserva el valor original', () => {
    expect(
      opcionesDePregunta({
        ...pregunta,
        choices: [
          { value: 'Pequeña', label: 'Small' },
          { value: 'Grande', label: 'Large' },
        ],
      }),
    ).toEqual([
      { valor: 'Pequeña', etiqueta: 'Small' },
      { valor: 'Grande', etiqueta: 'Large' },
    ]);
  });

  it('sin traducción usa el valor como etiqueta', () => {
    expect(opcionesDePregunta(pregunta)).toEqual([
      { valor: 'Pequeña', etiqueta: 'Pequeña' },
      { valor: 'Grande', etiqueta: 'Grande' },
    ]);
  });
});
