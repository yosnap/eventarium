import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import {
  type PoliticasPublicas,
  PublicPoliciesService,
} from '../../../core/policies/public-policies.service';
import { PublicPoliciesPage } from './public-policies-page';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

async function montar(datos: PoliticasPublicas): Promise<ComponentFixture<PublicPoliciesPage>> {
  TestBed.configureTestingModule({
    imports: [
      TranslocoTestingModule.forRoot({
        langs: { 'es-ES': es },
        translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
      }),
    ],
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: PublicPoliciesService, useValue: { obtener: vi.fn().mockResolvedValue(datos) } },
    ],
  });
  const fixture = TestBed.createComponent(PublicPoliciesPage);
  fixture.componentRef.setInput('slug', 'iawic-2026');
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

describe('PublicPoliciesPage', () => {
  it('pinta cada texto con su ancla y quién es responsable', async () => {
    const fixture = await montar({
      organization_name: 'IA Week',
      policies: [
        {
          version_id: 'v1',
          kind: 'condiciones',
          version: 1,
          content: '## Admisión\n\nSe pide **DNI**.',
          created_at: '2026-09-23T10:00:00Z',
        },
        {
          version_id: 'v2',
          kind: 'reembolsos',
          version: 3,
          content: 'Sin reembolsos <script>alert(1)</script>',
          created_at: '2026-09-23T10:00:00Z',
        },
      ],
    });
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('section#condiciones h2')?.textContent).toContain(
      'Condiciones del evento',
    );
    expect(raiz.querySelector('section#condiciones app-markdown-seguro strong')?.textContent).toBe(
      'DNI',
    );
    expect(raiz.querySelector('section#reembolsos')).not.toBeNull();
    expect(raiz.querySelector('script')).toBeNull();
    expect(raiz.textContent).toContain('Estas condiciones las fija IA Week, que es responsable');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('sin textos remite a las condiciones generales', async () => {
    const fixture = await montar({ organization_name: 'IA Week', policies: [] });
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('no ha publicado condiciones propias');
    expect(Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'))).toContain(
      '/legal/condiciones-de-inscripcion',
    );
  });
});
