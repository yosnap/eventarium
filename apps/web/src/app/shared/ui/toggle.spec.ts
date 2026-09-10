import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Toggle } from './toggle';

describe('Toggle', () => {
  let fixture: ComponentFixture<Toggle>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Toggle] }).compileComponents();
    fixture = TestBed.createComponent(Toggle);
    fixture.componentRef.setInput('label', 'Medición');
    fixture.componentRef.setInput('estado', 'No');
    fixture.detectChanges();
  });

  it('renderiza la etiqueta y expone `role="switch"` con `aria-checked` en el botón real', () => {
    const h4: HTMLElement = fixture.nativeElement.querySelector('h4');
    expect(h4.textContent).toContain('Medición');
    const boton: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    expect(boton.getAttribute('role')).toBe('switch');
    expect(boton.getAttribute('aria-checked')).toBe('false');
  });

  it('marca el interruptor al cambiar `checked` y actualiza el modelo al pulsar', () => {
    fixture.componentRef.setInput('checked', true);
    fixture.detectChanges();
    const boton: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    expect(boton.getAttribute('aria-checked')).toBe('true');

    boton.dispatchEvent(new Event('click'));
    fixture.detectChanges();
    expect(fixture.componentInstance.checked()).toBe(false);
  });

  it('respeta `disabled` y no alterna al pulsar', () => {
    fixture.componentRef.setInput('disabled', true);
    fixture.detectChanges();
    const boton: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    expect(boton.disabled).toBe(true);

    boton.dispatchEvent(new Event('click'));
    fixture.detectChanges();
    expect(fixture.componentInstance.checked()).toBe(false);
  });

  it('pinta el estado textual pasado por `estado`', () => {
    fixture.componentRef.setInput('estado', 'Siempre');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.sw-state')?.textContent).toBe('Siempre');
  });

  it('pinta la pista cuando se pasa `hint`', () => {
    fixture.componentRef.setInput('hint', 'Cuántas personas empiezan el formulario.');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.pista')?.textContent).toBe(
      'Cuántas personas empiezan el formulario.',
    );
  });
});
