import { ComponentFixture, TestBed } from '@angular/core/testing';

import { BrandMark } from './brand-mark';

describe('BrandMark', () => {
  let fixture: ComponentFixture<BrandMark>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [BrandMark] }).compileComponents();
    fixture = TestBed.createComponent(BrandMark);
  });

  it('pinta la inicial en mayúscula del nombre', () => {
    fixture.componentRef.setInput('nombre', 'eventarium');
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent?.trim()).toBe('E');
  });

  it('es decorativo: aria-hidden, no compite con el nombre textual que ya lo acompaña', () => {
    fixture.componentRef.setInput('nombre', 'IA Week Valencia');
    fixture.detectChanges();
    const span = (fixture.nativeElement as HTMLElement).querySelector('span');
    expect(span?.getAttribute('aria-hidden')).toBe('true');
  });
});
