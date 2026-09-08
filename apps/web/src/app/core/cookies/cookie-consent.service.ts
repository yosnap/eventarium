import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Injectable, PLATFORM_ID, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { CookieCategory, NON_ESSENTIAL_CATEGORIES } from './cookie-category';
import { DummyAnalyticsService } from './dummy-analytics.service';

const CLAVE_LOCAL_STORAGE = 'cookie-consent';

interface DecisionGuardada {
  readonly categories: CookieCategory[];
}

/**
 * Estado del banner de cookies: si ya se ha decidido, qué categorías están
 * activas, y el efecto de activar cada una (cargar los scripts no esenciales
 * correspondientes).
 *
 * Persistencia en `localStorage`, no en cookie: cada organización vive en su
 * propio host (`OrganizationDomain`), así que `localStorage` ya es por
 * organización sin ningún esfuerzo extra, igual que el resto del estado de
 * cliente de esta app.
 */
@Injectable({ providedIn: 'root' })
export class CookieConsentService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly dummyAnalytics = inject(DummyAnalyticsService);
  private readonly esNavegador = isPlatformBrowser(inject(PLATFORM_ID));

  private readonly decisionTomada = signal(false);
  private readonly categoriasActivas = signal<ReadonlySet<CookieCategory>>(
    new Set<CookieCategory>(['necessary']),
  );

  /** `true` mientras no haya una decisión guardada: el banner debe mostrarse.
   * Nunca en SSR: mostrar el banner solo tiene sentido con JavaScript activo
   * para poder decidir y persistir la respuesta. */
  readonly mostrarBanner = computed(() => this.esNavegador && !this.decisionTomada());
  readonly categorias = this.categoriasActivas.asReadonly();

  constructor() {
    if (!this.esNavegador) {
      return;
    }
    const guardada = this.leerDecisionGuardada();
    if (guardada) {
      this.decisionTomada.set(true);
      this.categoriasActivas.set(new Set(guardada.categories));
      this.activarScriptsDeLasCategorias(guardada.categories);
    }
  }

  async aceptarTodo(): Promise<void> {
    await this.decidir(['necessary', ...NON_ESSENTIAL_CATEGORIES]);
  }

  async rechazarTodo(): Promise<void> {
    await this.decidir(['necessary']);
  }

  async personalizar(categoriasElegidas: readonly CookieCategory[]): Promise<void> {
    await this.decidir(['necessary', ...categoriasElegidas.filter((c) => c !== 'necessary')]);
  }

  private async decidir(categorias: CookieCategory[]): Promise<void> {
    const unicas = [...new Set(categorias)];
    this.categoriasActivas.set(new Set(unicas));
    this.decisionTomada.set(true);
    this.guardarDecision(unicas);
    this.activarScriptsDeLasCategorias(unicas);

    try {
      await firstValueFrom(
        this.http.post(this.api.url('/public/cookie-consent'), { categories: unicas }),
      );
    } catch (error) {
      // La decisión ya se ha aplicado localmente (banner cerrado, scripts
      // activados o no según corresponda): un fallo de red al registrar el
      // consentimiento no debe bloquear la navegación de quien decide.
      console.error('[cookies] no se ha podido registrar el consentimiento:', error);
    }
  }

  private activarScriptsDeLasCategorias(categorias: readonly CookieCategory[]): void {
    if (categorias.includes('analytics')) {
      this.dummyAnalytics.activar();
    }
  }

  private leerDecisionGuardada(): DecisionGuardada | null {
    try {
      const bruto = localStorage.getItem(CLAVE_LOCAL_STORAGE);
      if (!bruto) {
        return null;
      }
      const decodificado: unknown = JSON.parse(bruto);
      if (
        decodificado &&
        typeof decodificado === 'object' &&
        Array.isArray((decodificado as DecisionGuardada).categories)
      ) {
        return decodificado as DecisionGuardada;
      }
      return null;
    } catch {
      return null;
    }
  }

  private guardarDecision(categorias: CookieCategory[]): void {
    try {
      localStorage.setItem(CLAVE_LOCAL_STORAGE, JSON.stringify({ categories: categorias }));
    } catch {
      // Almacenamiento no disponible (modo privado estricto, cuota agotada):
      // la decisión sigue aplicándose en esta visita, solo no persiste.
    }
  }
}
