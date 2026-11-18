import { Pipe, PipeTransform, inject } from '@angular/core';

import { IdiomaService } from './idioma.service';

/**
 * Enlace en el idioma de la página: `[routerLink]="'/eventos' | enlace"` lleva a
 * `/en/eventos` en una página en inglés. Puro: el idioma no cambia sin recargar.
 */
@Pipe({ name: 'enlace' })
export class EnlacePipe implements PipeTransform {
  private readonly idioma = inject(IdiomaService);

  transform(ruta: string): string;
  transform<T>(ruta: readonly T[]): (T | string)[];
  transform<T>(ruta: string | readonly T[]): string | (T | string)[] {
    return typeof ruta === 'string' ? this.idioma.enlace(ruta) : this.idioma.enlace(ruta);
  }
}
