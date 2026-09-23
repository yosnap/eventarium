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
 * `**palabra**` en el copy → `<strong class="landing-resaltado">`. Solo para
 * textos fijos de `es-ES.json`, nunca para contenido de la API ni del usuario:
 * `bypassSecurityTrustHtml` se salta el saneador de Angular, así que la única
 * protección es que todo el texto se escapa antes y la única etiqueta que se
 * genera es `strong`. El contenido que venga de la API va por
 * `markdownToSafeHtml`.
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
