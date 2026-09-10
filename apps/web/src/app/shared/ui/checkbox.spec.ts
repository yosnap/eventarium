import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Checkbox } from './checkbox';

describe('Checkbox', () => {
  let fixture: ComponentFixture<Checkbox>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Checkbox] }).compileComponents();
    fixture = TestBed.createComponent(Checkbox);
    fixture.componentRef.setInput('label', 'Acepto el tratamiento de mis datos');
    fixture.detectChanges();
  });

  it('renderiza la etiqueta como texto del <label>', () => {
    const label: HTMLLabelElement = fixture.nativeElement.querySelector('label');
    expect(label.textContent).toContain('Acepto el tratamiento de mis datos');
  });

  it('marca el checkbox al cambiar `checked` y actualiza el modelo al pulsar', () => {
    fixture.componentRef.setInput('checked', true);
    fixture.detectChanges();
    const input: HTMLInputElement = fixture.nativeElement.querySelector('input');
    expect(input.checked).toBe(true);

    input.checked = false;
    input.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(fixture.componentInstance.checked()).toBe(false);
  });

  it('respeta `disabled`', () => {
    fixture.componentRef.setInput('disabled', true);
    fixture.detectChanges();
    const input: HTMLInputElement = fixture.nativeElement.querySelector('input');
    expect(input.disabled).toBe(true);
  });

  it('pinta la pista cuando se pasa `hint`', () => {
    fixture.componentRef.setInput('hint', 'Obligatorio.');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.pista')?.textContent).toBe('Obligatorio.');
  });
});
