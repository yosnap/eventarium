import { Pipe, type PipeTransform, inject } from '@angular/core';
import { DomSanitizer, type SafeHtml } from '@angular/platform-browser';

const MARCADOR = /\*\*(.+?)\*\*/g;

function escapar(texto: string): string {
  return texto
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

/**
 * `**palabra**` en el copy → `<strong class="landing-resaltado">`. El texto
 * viene de `es-ES.json` (nuestro, no del usuario), pero se escapa igualmente y
 * solo se genera la etiqueta `strong`, que además pasa por el saneador de
 * Angular al enlazarse con `innerHTML`.
 */
@Pipe({ name: 'resaltar' })
export class ResaltarPipe implements PipeTransform {
  private readonly sanitizer = inject(DomSanitizer);

  transform(texto: string | null | undefined): SafeHtml {
    const html = escapar(texto ?? '').replace(
      MARCADOR,
      (_, palabra: string) => `<strong class="landing-resaltado">${palabra}</strong>`,
    );
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
