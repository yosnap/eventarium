import { HttpClient } from '@angular/common/http';
import {
  DestroyRef,
  PLATFORM_ID,
  type Signal,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { IdiomaService } from '../i18n/idioma.service';

/** Esperas entre consultas del estado, en ms; la última se repite. */
const ESPERAS = [2000, 4000, 8000];
/** Tiempo máximo esperando la traducción: después se queda el original. */
const LIMITE_MS = 60_000;

export interface OpcionesDeTraduccionEnVivo {
  /** Ruta de la API del recurso (`/public/organizations/acme/events/x`), o `null`. */
  readonly ruta: () => string | null;
  /** La API dice que la IA va a traducir lo pendiente (`translating`). */
  readonly pendiente: () => boolean;
  /** Vuelve a pedir los datos de la página, ya traducidos. */
  readonly recargar: () => Promise<void>;
}

/**
 * Traducción al vuelo de una página pública. Devuelve `true` mientras se
 * traduce: la página enseña un esqueleto en lugar del texto original.
 *
 * - En el servidor no hace nada: el SSR pinta el esqueleto y el navegador
 *   continúa (así no salta de original a esqueleto).
 * - En el navegador pide la traducción (POST) y consulta el estado con espera
 *   progresiva; con la pestaña oculta no consulta.
 * - Al terminar recarga los datos; si falla o pasa el límite, se queda el
 *   original. Nunca deja un bloque vacío.
 */
export function traduccionEnVivo(opciones: OpcionesDeTraduccionEnVivo): Signal<boolean> {
  const http = inject(HttpClient);
  const api = inject(ApiService);
  const idioma = inject(IdiomaService).idioma();
  const navegador = isPlatformBrowser(inject(PLATFORM_ID));
  const terminada = signal(false);
  let cancelada = false;
  let iniciada: string | null = null;
  inject(DestroyRef).onDestroy(() => (cancelada = true));

  const esperar = (ms: number) =>
    new Promise<void>((resolver) => {
      const tic = () => {
        if (cancelada || typeof document === 'undefined' || !document.hidden) {
          resolver();
        } else {
          setTimeout(tic, 1000);
        }
      };
      setTimeout(tic, ms);
    });

  async function seguir(ruta: string): Promise<void> {
    const parametros = { params: { locale: idioma } };
    try {
      const pedida = await firstValueFrom(
        http.post<{ queued: boolean }>(api.url(`${ruta}/translations`), null, parametros),
      );
      if (!pedida.queued) {
        return;
      }
      const inicio = Date.now();
      for (let intento = 0; !cancelada && Date.now() - inicio < LIMITE_MS; intento++) {
        await esperar(ESPERAS[Math.min(intento, ESPERAS.length - 1)]!);
        if (cancelada) {
          return;
        }
        const estado = await firstValueFrom(
          http.get<{ in_progress: boolean }>(api.url(`${ruta}/translations/status`), parametros),
        );
        if (!estado.in_progress) {
          await opciones.recargar();
          return;
        }
      }
    } catch {
      // Sin traducción: se queda el original.
    } finally {
      if (!cancelada) {
        terminada.set(true);
      }
    }
  }

  effect(() => {
    const ruta = opciones.ruta();
    const pendiente = opciones.pendiente();
    untracked(() => {
      if (!navegador || !ruta || !pendiente || iniciada === ruta) {
        return;
      }
      iniciada = ruta;
      terminada.set(false);
      void seguir(ruta);
    });
  });

  return computed(() => opciones.pendiente() && !terminada());
}
