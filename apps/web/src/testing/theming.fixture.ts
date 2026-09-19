import { computed, signal } from '@angular/core';

import { Branding } from '../app/core/theming/branding.model';
import { brandingDePrueba as brandingDePruebaBase } from './branding.fixture';

/**
 * Doble mínimo de `ThemingService` para los tests de componentes.
 *
 * Sin él, un componente con la cabecera pública inyectaría el servicio real,
 * que necesita `HttpClient` y hace una petición. Se deriva todo del `branding`
 * reactivo —igual que el servicio real— para que cambiar el branding durante
 * un test se refleje en las señales derivadas.
 *
 * Se centraliza aquí porque el mismo doble aparecía copiado en una decena de
 * specs: al cambiar el contrato de branding, cada copia había que actualizarla
 * por separado.
 */
export function themingDePrueba(branding: Branding = brandingDePruebaBase()) {
  const estado = signal<Branding>(branding);

  return {
    estado,
    branding: estado.asReadonly(),
    error: signal<string | null>(null),
    plataforma: computed(() => estado().platform),
    nombreDeMarca: computed(() => estado().platform.name),
  };
}
