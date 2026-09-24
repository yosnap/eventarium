import { DOCUMENT, DestroyRef, Injectable, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

import { applyTokensDeEvento } from './apply-tokens';
import type { PlantillaDeTema } from './theme-template.model';

/**
 * Quién tiene puesto el tema de evento en `<body>` y cuál fue el último.
 *
 * Existe para que navegar entre páginas del mismo evento no parpadee: al
 * cambiar de página, el router destruye la anterior (que quitaba el tema) y la
 * nueva no lo volvía a poner hasta que respondía la API. Ahora la nueva lo
 * pone al construirse si es del mismo evento, y la limpieza se aplaza a una
 * microtarea: si en ese intervalo se ha abierto otra página de evento, no se
 * quita nada.
 */
@Injectable({ providedIn: 'root' })
export class AmbitoDeEvento {
  private readonly documento = inject(DOCUMENT);
  private paginasAbiertas = 0;
  private ultimo: { readonly slug: string; readonly tema: PlantillaDeTema | null } | null = null;

  abrir(slug: string | null): void {
    this.paginasAbiertas++;
    if (!this.ultimo) {
      // Primera página de evento de la visita: se deja lo que haya pintado
      // el SSR hasta que lleguen los datos.
      return;
    }
    this.pintar(this.ultimo.slug === slug ? this.ultimo.tema : null);
  }

  aplicar(slug: string | null, tema: PlantillaDeTema | null): void {
    this.ultimo = slug ? { slug, tema } : null;
    this.pintar(tema);
  }

  cerrar(): void {
    this.paginasAbiertas--;
    queueMicrotask(() => {
      if (this.paginasAbiertas === 0) {
        this.pintar(null);
      }
    });
  }

  private pintar(tema: PlantillaDeTema | null): void {
    applyTokensDeEvento(tema ? { theme: tema } : null, this.documento);
  }
}

/**
 * Para las páginas de un evento (ficha, inscripción, programa, sesión,
 * patrocinador, políticas): mantienen la plantilla del evento al navegar
 * dentro de él.
 *
 * Se llama en el constructor (contexto de inyección). Devuelve la función que
 * aplica el tema al llegar los datos; la limpieza al destruir la página queda
 * registrada, porque `<body>` sobrevive a la navegación SPA.
 */
export function temaDeEvento(): (tema: PlantillaDeTema | null | undefined) => void {
  const ambito = inject(AmbitoDeEvento);
  const slug = inject(ActivatedRoute).snapshot.paramMap.get('slug');
  // Las peticiones no se cancelan al salir: una respuesta que llega con la
  // página ya destruida no debe volver a poner su tema en otra página.
  let viva = true;
  ambito.abrir(slug);
  inject(DestroyRef).onDestroy(() => {
    viva = false;
    ambito.cerrar();
  });
  return (tema) => {
    if (viva) {
      ambito.aplicar(slug, tema ?? null);
    }
  };
}
