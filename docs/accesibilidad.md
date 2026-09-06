# Accesibilidad

El compromiso del proyecto es **WCAG 2.1 nivel AA en toda la aplicación**, incluido el
panel de administración (PRD §6). No es una aspiración: es una puerta de calidad que
bloquea la integración continua.

## Cómo se verifica

| Comprobación | Herramienta | Dónde se ejecuta |
|---|---|---|
| Violaciones automáticas | `axe-core` sobre las reglas `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` | `pnpm test` (Vitest) y CI |
| Reglas de plantilla | `angular-eslint` con `templateAccessibility` | `pnpm lint` y CI |
| Revisión manual | Checklist de esta página | Antes de cerrar cada fase |

**Criterio de fallo: cualquier violación de axe, del impacto que sea.** No se filtra por
severidad. Una violación «menor» sigue siendo una barrera real para alguien, y filtrar
por impacto convierte la puerta en una recomendación.

`src/testing/axe.ts` fija el conjunto de reglas de forma explícita en lugar de usar el
predeterminado de axe, para que una actualización de la librería no cambie en silencio
lo que se exige.

## Decisiones de diseño con impacto en accesibilidad

- **Foco visible** (2.4.7): `:focus-visible` con contorno de 3 px sobre el color
  primario, definido globalmente en `src/styles.css`. Nunca se elimina el contorno.
- **Salto al contenido** (2.4.1): enlace `.skip-link` como primer elemento de cada
  shell, oculto hasta recibir el foco.
- **Regiones** (1.3.1): `header`, `nav` con `aria-label`, `main` y `footer` en los dos
  shells. `main` tiene `tabindex="-1"` para poder recibir el foco desde el salto.
- **Formularios** (1.3.1, 3.3.1, 3.3.2): `app-input` enlaza `label` con `for`/`id` y el
  mensaje de error con `aria-describedby` + `aria-invalid`. La validación es propia y no
  la nativa del navegador, cuyos mensajes no se pueden traducir ni asociar al campo.
- **Mensajes de estado** (4.1.3): `app-alert` usa `role="alert"` para errores y
  `role="status"` para el resto, para no interrumpir la lectura sin motivo.
- **Objetivo táctil** (2.5.5): botones y campos con 44 px de alto mínimo.
- **Movimiento** (2.3.3): `prefers-reduced-motion` anula animaciones y transiciones.
- **Contraste** (1.4.3): la paleta por defecto cumple AA. Como el branding lo elige cada
  organización, `core/theming/contrast.ts` calcula la razón de contraste de los pares
  críticos y el panel avisa cuando alguno baja de 4,5:1.
- **Idioma** (3.1.1): `<html lang="es-ES">`; todos los textos vienen de
  `public/assets/i18n/es-ES.json`, ninguno está incrustado en las plantillas.

## Checklist manual — Fase 0

Revisado el 2026-09-07 sobre las pantallas existentes: portada pública (plantillas
`classic` y `minimal`), acceso al panel, escritorio e identidad visual.

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 1.1.1 | Contenido no textual | El logotipo lleva `alt` con el nombre de la organización; las muestras de color son decorativas y llevan `aria-hidden` | ✅ |
| 1.3.1 | Información y relaciones | Landmarks, encabezados en orden, etiquetas asociadas a los campos | ✅ |
| 1.4.3 | Contraste mínimo | Paleta por defecto y paleta demo verificadas con el cálculo de `contrast.ts`; el panel avisa si el branding no cumple | ✅ |
| 1.4.4 | Redimensionar texto | Zoom del navegador al 200 %: sin pérdida de contenido ni scroll horizontal (unidades relativas en toda la hoja de estilos) | ✅ |
| 1.4.10 | Reajuste | A 320 px de ancho el panel pasa a una sola columna (`@media (max-width: 48rem)`) | ✅ |
| 2.1.1 | Teclado | Recorrido completo con tabulador: salto al contenido, navegación, formulario de acceso, cierre de sesión. Sin trampas de foco | ✅ |
| 2.4.1 | Evitar bloques | Enlace de salto al contenido en ambos shells | ✅ |
| 2.4.2 | Título de página | `ThemingService` fija `document.title` con el nombre de la organización | ✅ |
| 2.4.7 | Foco visible | Contorno de 3 px en todos los elementos interactivos | ✅ |
| 2.5.5 | Tamaño del objetivo | Botones y campos de 44 px de alto | ✅ |
| 3.1.1 | Idioma de la página | `lang="es-ES"` | ✅ |
| 3.3.1 | Identificación de errores | El error de acceso se anuncia con `role="alert"`; los de campo, con `aria-describedby` | ✅ |
| 3.3.2 | Etiquetas o instrucciones | Todos los campos tienen etiqueta visible | ✅ |
| 4.1.2 | Nombre, función, valor | `aria-busy` durante el envío; `aria-invalid` en campos con error; botones con texto | ✅ |
| 4.1.3 | Mensajes de estado | `role="status"` para avisos no críticos | ✅ |

### Pendiente para fases posteriores

- Revisión con lector de pantalla real (VoiceOver y NVDA) sobre los flujos de
  inscripción, que todavía no existen.
- Comprobar el contraste de las plantillas públicas nuevas según se añadan al registro.

## Al añadir una pantalla

1. Externaliza todos los textos a `es-ES.json`.
2. Usa los componentes de `shared/ui`, que ya resuelven etiquetas, errores y foco.
3. Añade un test que llame a `esperarSinViolacionesDeAccesibilidad`.
4. Recorre la pantalla solo con teclado.
5. Añade la fila correspondiente al checklist de esta página.
