/**
 * Precarga de las fuentes que usa la página.
 *
 * Las familias se declaran con `font-display: swap`: sin precarga, el navegador
 * pinta primero con una fuente del sistema y la cambia al llegar el `.woff2`. Se
 * nota en cada carga completa, también al cambiar de idioma, que recarga la página.
 * Con `<link rel="preload">` en el `<head>`, el fichero se pide antes del primer
 * pintado y, si está en caché, ya no hay salto.
 *
 * Las familias salen del tema que el SSR ya ha pintado en el HTML (`--font-display`
 * y `--font-body`), con las de `typography.css` como valor por defecto. Solo se
 * precarga el peso con el que se pinta el texto normal de cada familia.
 */
const FICHERO_POR_FAMILIA: Readonly<Record<string, string>> = {
  'Bebas Neue': '/assets/fonts/bebas-neue/bebas-neue-400.woff2',
  'Archivo Black': '/assets/fonts/archivo-black/archivo-black-400.woff2',
  Oswald: '/assets/fonts/oswald/oswald-500.woff2',
  'Playfair Display': '/assets/fonts/playfair-display/playfair-display-600.woff2',
  'DM Sans': '/assets/fonts/dm-sans/dm-sans-400.woff2',
  Inter: '/assets/fonts/inter/inter-400.woff2',
  Lora: '/assets/fonts/lora/lora-400.woff2',
};

const POR_DEFECTO = { display: 'Bebas Neue', body: 'DM Sans' };

const TOKEN = /--font-(display|body):\s*'?([^;'"]+?)'?\s*;/g;

export function fuentesDelHtml(html: string): string[] {
  const familias = new Set<string>();
  const vistas = { display: false, body: false };
  for (const [, token, familia] of html.matchAll(TOKEN)) {
    if (FICHERO_POR_FAMILIA[familia]) {
      familias.add(familia);
      vistas[token as 'display' | 'body'] = true;
    }
  }
  if (!vistas.display) familias.add(POR_DEFECTO.display);
  if (!vistas.body) familias.add(POR_DEFECTO.body);
  return [...familias].map((familia) => FICHERO_POR_FAMILIA[familia]);
}

export function precargarFuentes(html: string): string {
  const fin = html.indexOf('</head>');
  if (fin === -1) {
    return html;
  }
  const enlaces = fuentesDelHtml(html)
    .filter((fichero) => !html.includes(`href="${fichero}"`))
    .map(
      (fichero) => `<link rel="preload" href="${fichero}" as="font" type="font/woff2" crossorigin>`,
    )
    .join('');
  return `${html.slice(0, fin)}${enlaces}${html.slice(fin)}`;
}
