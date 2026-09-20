import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, Type, provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Dialog } from './dialog';
import { KpiCard } from './kpi-card';
import { PageHeader } from './page-header';
import { Panel } from './panel';
import { SegmentedFilter } from './segmented-filter';
import { TableToolbar } from './table-toolbar';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';

const TEMAS = ['oscuro', 'claro'] as const;

function fijarTema(tema: (typeof TEMAS)[number]): void {
  if (tema === 'claro') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}

@Component({
  selector: 'app-anfitrion-cabecera',
  imports: [PageHeader],
  template: `
    <app-page-header rotulo="Inscripciones">
      Hay <span class="mark">14 solicitudes</span> esperando tu decisión
      <button acciones type="button">Ver página pública</button>
    </app-page-header>
  `,
})
class AnfitrionCabecera {}

@Component({
  selector: 'app-anfitrion-panel',
  imports: [Panel, TableToolbar, SegmentedFilter],
  template: `
    <app-panel>
      <div cabecera><span class="rotulo-seccion">Solicitudes</span></div>
      <div class="panel-cuerpo">
        <app-table-toolbar [(busqueda)]="busqueda" placeholderBusqueda="Buscar por nombre o correo">
          <app-segmented-filter
            [opciones]="[
              { valor: 'todas', etiqueta: 'Todas' },
              { valor: 'pendientes', etiqueta: 'Pendientes' },
            ]"
            [valor]="filtro"
            etiqueta="Filtrar por estado"
            (cambio)="filtro = $event"
          />
        </app-table-toolbar>
      </div>
      <div pie><span>Total</span><strong>382</strong></div>
    </app-panel>
  `,
})
class AnfitrionPanel {
  busqueda = '';
  filtro = 'todas';
}

/** jsdom no implementa showModal/close: se sustituyen como en event-payments.spec. */
function stubDeDialogoNativo(): void {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      this.removeAttribute('open');
    };
  }
}

@Component({
  selector: 'app-anfitrion-dialogo',
  imports: [Dialog],
  template: `
    <button type="button" id="abridor" (click)="dialogo.abrir()">Abrir</button>
    <app-dialog #dialogo (cerrado)="cierres = cierres + 1">
      <h3>¿Confirmar?</h3>
      <div pie>PIE</div>
    </app-dialog>
  `,
})
class AnfitrionDialogo {
  cierres = 0;
}

function montar<T>(componente: Type<T>): Promise<ComponentFixture<T>> {
  const fixture = TestBed.createComponent(componente);
  return fixture.whenStable().then(() => fixture);
}

describe('patrones de panel (fase 0, plan 260915-0052)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('la cabecera de página es accesible en ambos temas', async () => {
    for (const tema of TEMAS) {
      fijarTema(tema);
      const fixture = await montar(AnfitrionCabecera);
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    }
  });

  it('la cabecera expone rótulo, titular y acción', async () => {
    const fixture = await montar(AnfitrionCabecera);
    const texto = fixture.nativeElement.textContent;
    // El rótulo va en minúsculas en el DOM: las mayúsculas son CSS
    // (text-transform), que textContent no refleja.
    expect(texto).toContain('Inscripciones');
    expect(texto).toContain('14 solicitudes');
    // La acción viaja en la ranura derecha, dentro de la cabecera.
    const accion = fixture.nativeElement.querySelector('header [acciones]');
    expect(accion?.textContent).toContain('Ver página pública');
  });

  it('la tarjeta KPI pinta rótulo, valor y descriptor, accesible en ambos temas', async () => {
    for (const tema of TEMAS) {
      fijarTema(tema);
      const fixture = TestBed.createComponent(KpiCard);
      fixture.componentRef.setInput('rotulo', 'Por aprobar');
      fixture.componentRef.setInput('valor', '14');
      fixture.componentRef.setInput('descriptor', 'El tono avisa; el rótulo informa');
      fixture.componentRef.setInput('tono', 'warn');
      await fixture.whenStable();
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
      expect(fixture.nativeElement.textContent).toContain('Por aprobar');
      expect(fixture.nativeElement.textContent).toContain('14');
    }
  });

  it('el panel con cabecera, toolbar y pie es accesible y filtra', async () => {
    for (const tema of TEMAS) {
      fijarTema(tema);
      const fixture = await montar(AnfitrionPanel);
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    }

    const fixture = await montar(AnfitrionPanel);
    const nativo = fixture.nativeElement;

    // Filtro segmentado: grupo etiquetado, opción activa con aria-pressed.
    const grupo = nativo.querySelector('[role="group"]');
    expect(grupo?.getAttribute('aria-label')).toBe('Filtrar por estado');
    const botones = Array.from(grupo.querySelectorAll('button')) as HTMLButtonElement[];
    expect(botones[0].getAttribute('aria-pressed')).toBe('true');
    expect(botones[1].getAttribute('aria-pressed')).toBe('false');

    botones[1].click();
    await fixture.whenStable();
    expect(fixture.componentInstance.filtro).toBe('pendientes');

    // La búsqueda escribe en el modelo.
    const busqueda = nativo.querySelector('input[type="search"]');
    busqueda.value = 'ana';
    busqueda.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    expect(fixture.componentInstance.busqueda).toBe('ana');

    // El pie pinta el total.
    expect(nativo.textContent).toContain('Total');
    expect(nativo.textContent).toContain('382');
  });

  it('el panel sin cabecera ni pie deja las franjas vacías (ocultas por CSS :empty)', async () => {
    const fixture = TestBed.createComponent(Panel);
    await fixture.whenStable();
    const nativo = fixture.nativeElement;
    // Las franjas existen en el DOM pero sin ningún nodo dentro: el :empty del
    // componente las oculta visualmente (mismo patrón que .acciones de card.ts).
    const franjas = [
      nativo.querySelector('.panel__head') as HTMLElement,
      nativo.querySelector('.panel__pie') as HTMLElement,
    ];
    for (const franja of franjas) {
      expect(franja).not.toBeNull();
      expect(franja.childElementCount).toBe(0);
      expect(franja.textContent).toBe('');
    }
  });

  it('el diálogo abre, cierra y emite su cierre', async () => {
    stubDeDialogoNativo();
    const fixture = await montar(AnfitrionDialogo);
    const nativo = fixture.nativeElement;
    const dialogo = nativo.querySelector('dialog') as HTMLDialogElement;
    const abridor = nativo.querySelector('#abridor') as HTMLButtonElement;

    expect(dialogo.hasAttribute('open')).toBe(false);

    abridor.click();
    await fixture.whenStable();
    expect(dialogo.hasAttribute('open')).toBe(true);

    // Escape viaja como cancelación del nativo, y el cierre emite (cerrado).
    dialogo.dispatchEvent(new Event('cancel'));
    await fixture.whenStable();
    expect(dialogo.hasAttribute('open')).toBe(false);
    expect(fixture.componentInstance.cierres).toBe(1);
  });
});
