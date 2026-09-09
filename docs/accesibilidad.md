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

## Checklist manual — Fase 1 (correo y verificación)

Revisado el 2026-09-07 sobre `/registro` y `/verificar-correo`.

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 2.1.1 | Teclado | Recorrido completo con tabulador en ambas pantallas: campos, envío, enlace a «ya tienes cuenta» | ✅ |
| 3.3.1 | Identificación de errores | Errores de campo con `aria-describedby`/`aria-invalid` (mismo patrón que `admin/login`) | ✅ |
| 4.1.3 | Mensajes de estado | El resultado de la verificación (éxito, enlace caducado) se anuncia con `aria-live="assertive"`: no ocurre por ninguna interacción del usuario, así que sin esto un lector de pantalla no se entera de que la comprobación terminó | ✅ |
| 1.4.1 | Uso del color | El indicador de fuerza de contraseña (`shared/ui/password-strength.ts`) no depende solo del color de la barra: cada requisito lleva además un texto «cumplido»/«pendiente». Sin `aria-live` a propósito: anunciar en cada pulsación sería disruptivo | ✅ |
| — | Cobertura automática | `register-page.spec.ts` y `verify-email-page.spec.ts`: cero violaciones de axe en los tres estados de cada pantalla (formulario, éxito, error), incluido el formulario con el indicador de fuerza visible | ✅ |

**Turnstile (widget de terceros, fuera del alcance de axe): pendiente de verificación
manual con lector de pantalla real.** El desarrollo corre con `TURNSTILE_ENABLED=false`
(decisión de producto), así que el iframe de Cloudflare nunca se ha renderizado en esta
fase — no hay una clave de sitio real disponible en este entorno. Antes de activar
Turnstile en producción, alguien con VoiceOver o NVDA debe comprobar sobre un entorno
con `TURNSTILE_ENABLED=true` y una `TURNSTILE_SITE_KEY` real que: el widget se anuncia
como un control identificable, es alcanzable y operable por teclado, y no bloquea el
envío del formulario cuando el desafío se completa correctamente. Esta fila se marca
como pendiente, no como comprobada, hasta que esa verificación ocurra.

## Checklist manual — Fase 3 (panel de organización y branding)

Revisado el 2026-09-07 sobre `admin/organization` (nueva) y `admin/branding` (pasa de
solo lectura a formulario de edición completo: plantilla, logo, colores, tipografías,
redes sociales y resumen del organizador).

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 1.3.1 | Información y relaciones | Los nuevos campos usan `app-input`/`app-textarea` (mismo patrón de etiqueta+error+ayuda que el resto del panel); cada muestra de color editable lleva `aria-label` propio, distinto del campo de texto hermano | ✅ |
| 1.4.3 | Contraste mínimo | El aviso de `checkBrandingContrast` se calcula ahora sobre los valores **en edición**, no solo sobre lo ya publicado — se comprueba con test que aparece y desaparece al corregir un color | ✅ |
| 3.3.1 | Identificación de errores | El nombre de la organización y el logotipo con tipo no permitido muestran su error junto al campo, sin depender del color | ✅ |
| 3.3.2 | Etiquetas o instrucciones | Selector de plantilla y campo de fichero llevan `<label for>` explícito, no solo el título de la tarjeta | ✅ |
| — | Cobertura automática | `organization-page.spec.ts` (3 tests) y `branding-page.spec.ts` (4 tests): cero violaciones de axe al cargar, tras guardar con éxito, y con el aviso de contraste visible | ✅ |

**Pendiente de esta fase**: recorrido manual con solo teclado y con lector de pantalla
real sobre estas dos pantallas — el entorno de desarrollo local no tenía forma de
navegar al subdominio de una organización de autoservicio sin modificar la resolución
de nombres del sistema (`DOMINIO_BASE` vacío en desarrollo, ver `docs/despliegue.md`),
así que la verificación de esta fase se apoyó en la cobertura automática de axe y en
comprobar el contrato de los endpoints (`GET/PATCH /organizations/me`,
`GET/PUT /organizations/me/branding`, `PUT .../branding/logo`) directamente. Queda
pendiente el recorrido manual antes de dar la fase por cerrada de cara a producción.

## Checklist manual — Fase 4 (roles, campos de perfil y miembros)

Revisado el 2026-09-07 sobre `admin/roles`, `admin/roles/:id` (crear y editar),
`admin/members` y `admin/members/nuevo`.

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 1.3.1 | Información y relaciones | Cada control de campo dinámico (`shared/ui/dynamic-field.ts`) enlaza etiqueta, ayuda y error igual que `app-input`/`app-textarea`, sea cual sea su tipo (texto, selector, casilla…) | ✅ |
| 2.4.3 | Orden del foco | El resumen de errores (`shared/ui/error-summary.ts`) enlaza cada entrada al campo real con `href="#id"`, no a un elemento decorativo — encontrado y corregido un fallo real donde `[id]` en `app-input`/`app-textarea` se reflejaba también como atributo nativo en el elemento anfitrión, produciendo un `id` duplicado en el DOM que rompía el enlace; el `input` pasó a llamarse `fieldId` para evitar la colisión con el atributo global `id` | ✅ |
| 3.3.1 | Identificación de errores | Con varios errores a la vez (varios campos de perfil obligatorios sin rellenar), aparece el resumen enlazado además del error inline en cada campo — antes de esta fase solo existía el error inline | ✅ |
| 4.1.2 | Nombre, función, valor | Los permisos que el actor no posee se muestran deshabilitados con el motivo en `title`, en vez de ocultarse — decisión que resuelve la contradicción entre el `Requirements` y el `Risk Assessment` del plan de esta fase a favor de mostrar y explicar, no ocultar | ✅ |
| — | Cobertura automática | 6 ficheros de test nuevos (roles, miembros, `dynamic-field`, `error-summary`, validación de campos dinámicos): cero violaciones de axe en listado, creación, edición y con el resumen de errores visible | ✅ |

**Hallazgo real corregido durante la verificación manual, no solo en las pruebas**:
los selectores nativos (`<select>`) que reciben su valor inicial de una respuesta de la
API en vez de la propia interacción de la persona (tipo de campo al empezar un rol
desde plantilla, plantilla de identidad visual) mostraban visualmente la primera
opción de la lista en vez de la que correspondía, aunque el dato interno fuera
correcto — un `<select [value]="…">` con `<option>` generadas por `@for` no garantiza
que el navegador aplique el valor si las opciones aún no existen en ese ciclo de
detección de cambios. Se sustituyó por `[selected]` en cada `<option>`, más fiable
para listas de opciones dinámicas. Verificado leyendo `select.value` desde la consola
del navegador antes y después de la corrección, sobre un rol creado a partir de la
plantilla «Voluntariado».

## Checklist manual — Fase 5 (cuenta propia y recuperación)

Revisado el 2026-09-07 sobre `/recuperar-contrasena`, `/recuperar-contrasena/nueva`,
`/cuenta/confirmar-correo` y `admin/account`, más el selector de organización en
`admin-shell`.

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 2.1.1 | Teclado | Recorrido completo con tabulador en las cuatro pantallas nuevas: campos, envío, enlaces de vuelta | ✅ |
| 3.3.1 | Identificación de errores | Mismo patrón `aria-describedby`/`aria-invalid` que el resto del panel en los formularios de perfil, correo y contraseña de `account-page` | ✅ |
| 4.1.3 | Mensajes de estado | El resultado de `reset-password-page` y `confirm-email-change-page` (éxito, token caducado) se anuncia con `aria-live="assertive"`, mismo patrón que `verify-email-page`: ninguna de las dos comprobaciones ocurre por interacción directa de la persona | ✅ |
| 2.4.4 | Propósito de los enlaces | El selector de organización usa `<a href>` reales por organización (no un manejador de clic que cambia `location.href`), con `aria-label` en el `nav` que lo contiene — un enlace real se anuncia como navegación, no como un control genérico | ✅ |
| 1.3.1 | Información y relaciones | Los enlaces sociales de `account-page` reutilizan `app-input` con su etiqueta ya asociada; el guardado ocurre al perder el foco (`blurred`), sin depender de un botón adicional por fila | ✅ |
| — | Cobertura automática | 4 ficheros de test nuevos (`forgot-password-page`, `reset-password-page`, `confirm-email-change-page`, `account-page`): cero violaciones de axe en cada estado (formulario, éxito, error, token caducado) | ✅ |

**Verificación de extremo a extremo realizada manualmente** (no solo declarada, según
exige el paso de cierre de esta fase): recuperación de contraseña completa contra el entorno de
desarrollo real (Caddy + Angular SSR + FastAPI + Redis + Mailpit) — solicitud del
enlace, lectura del correo real en Mailpit, cambio de contraseña, inicio de sesión con
la contraseña nueva, edición del perfil y guardado de un enlace social, todo
comprobado en el navegador. Este recorrido encontró y permitió corregir dos fallos
reales que ningún test unitario cubría: la migración `0008_cuenta_y_recuperacion` no
se había aplicado a la base de datos de desarrollo (solo a la de test), y
`account-page` no recargaba el usuario actual tras una recarga completa de página
(`AuthService.refresh()` solo renueva el token, no el usuario en memoria) — corregido
con `AuthService.loadCurrentUser()`.

## Checklist manual — Fase 2 del PRD, fase 4 (página pública con SSR)

Revisado el 2026-09-08 sobre las cuatro pantallas públicas nuevas:
`/eventos` (listado), `/eventos/:slug` (detalle con agenda), `/eventos/:slug/sesiones/:sessionId`
(ponencia) y `/ponentes/:publicSlug` (perfil de ponente).

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 1.3.1 | Información y relaciones | Landmarks heredados de `PublicShell`; encabezados jerárquicos (`h1` del recurso, `h2` de sus secciones); redes sociales del ponente en un `nav` con `aria-label` propio | ✅ |
| 2.4.4 | Propósito de los enlaces | Cada participante con perfil público enlaza a `/ponentes/:slug` con su nombre real como texto del enlace, nunca "ver más"; el historial del ponente enlaza a cada evento y cada sesión por su título | ✅ |
| 1.1.1 / 4.1.2 | Contenido no textual / nombre, función, valor | El `iframe` del vídeo embebido lleva `title` traducido; el enlace directo para la plataforma «otro» usa un texto descriptivo, no la URL cruda | ✅ |
| 4.1.3 | Mensajes de estado | El error de carga (`EventsListPage`) usa `app-alert` con `role="alert"`, mismo patrón que el resto del proyecto | ✅ |
| — | Cobertura automática | 4 ficheros de test nuevos (`event-page`, `session-page`, `speaker-page`, `events-list-page`): cero violaciones de axe en cada estado (contenido, "no encontrado", listado vacío) | ✅ |

**Hallazgo real corregido durante la verificación automática**: la agenda de
`EventPage` envolvía cada `<app-card>` directamente dentro de un `<ul>`
(`app-card` renderiza su propio `<section>` raíz), lo que viola 1.3.1 — un `<ul>`
solo puede contener `<li>` como hijo directo. Corregido envolviendo cada tarjeta en
su propio `<li>`, detectado por `esperarSinViolacionesDeAccesibilidad` antes de
llegar a revisión manual.

**Excluido de la cobertura automática, verificado solo manualmente**: axe-core no
puede analizar un `<iframe>` a un dominio real (`youtube-nocookie.com`) dentro del
entorno de test (jsdom) — falla al intentar comunicarse con su `contentWindow`. El
`title` del `iframe` y el resto de la pantalla se verificaron por separado con el
caso de la plataforma «otro» (sin `iframe` real), que sí corre bajo axe.

**Verificación de extremo a extremo realizada manualmente** contra el entorno de
desarrollo real (API + Postgres + servidor SSR de Angular, `node
dist/web/server/server.mjs`), con `curl` fijando `X-Forwarded-Host` para no
depender de resolución de nombres local: evento publicado con agenda de una
sesión, ponente activando su propio perfil público en autoservicio (no desde el
panel), y comprobación de que el HTML servido antes de cualquier hidratación ya
trae el título, las etiquetas OG (`og:title`, `og:description`) y el contenido de
la agenda y del ponente. Confirmado también el código de estado real: `404` para
un evento en borrador, para un slug inexistente y para un ponente sin perfil
activo; `200` con contenido para el evento, la sesión y el ponente publicados; y
aislamiento multi-tenant end-to-end (el mismo evento pedido con el host de otra
organización responde `404`, no solo a nivel de API sino a través de todo el
recorrido de SSR).

## Checklist manual — Fase 5 del PRD, fase 2 (patrocinadores)

Revisado el 2026-09-08 sobre las tres pantallas nuevas: `/admin/sponsor-tiers`
(niveles de la organización), el bloque de patrocinadores embebido en
`/admin/events/:id` (`EventSponsors`) y el bloque público en
`/eventos/:slug`.

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 2.1.1 / 2.5.5 | Teclado / objetivo táctil | Reordenar niveles usa botones «↑»/«↓» (`app-button`, 2.75rem de alto mínimo), nunca arrastrar y soltar sin alternativa por teclado | ✅ |
| 4.1.2 | Nombre, función, valor | Los botones de reordenar llevan `aria-label` con el nombre del nivel (`"Subir Oro"`/`"Bajar Oro"`), no solo la flecha visual | ✅ |
| 1.1.1 | Contenido no textual | Cada logo de patrocinador (panel y bloque público) lleva `alt` con el nombre del patrocinador; sin logo, se muestra el nombre como texto | ✅ |
| 4.1.3 | Mensajes de estado | Errores de carga/guardado con `app-alert`, mismo patrón que el resto del panel | ✅ |
| — | Cobertura automática | 3 ficheros de test nuevos (`sponsor-tiers-page`, `event-sponsors`, `event-page` ampliado): cero violaciones de axe en cada estado con datos (niveles reordenados, patrocinador monetario/en especie, bloque público agrupado) | ✅ |

**Decisión de diseño con impacto en accesibilidad**: reordenar con dos
llamadas `PATCH` secuenciales (intercambiar `display_order` entre el nivel
movido y su vecino) en vez de arrastrar y soltar evita por completo el
problema de accesibilidad del drag-and-drop (WCAG 2.5.7, objetivos de
arrastre) — no hay nada que arrastrar, cada movimiento es una acción de
botón discreta y anunciable.

## Checklist manual — Fase 5 del PRD, fase 3 (legal, cookies y consentimientos)

Revisado el 2026-09-08 sobre el banner de cookies (`shared/cookies/cookie-banner.ts`,
integrado en `layouts/public/public-shell.ts`), las cuatro páginas legales públicas
(`/legal/*`) y su editor en el panel (`/admin/legal`).

**Orejime vs. Klaro, decisión tomada en esta fase.** `docs/prd.md` §7 dejaba el
banner "a confirmar frente a Klaro según auditoría WCAG". Comprobación rápida
(no una auditoría exhaustiva): Orejime es un fork de Klaro nacido explícitamente
para corregir problemas de accesibilidad de Klaro (gestión de foco al abrir/cerrar,
navegación por teclado del panel de personalización) documentados por su propio
proyecto. Ninguna de las dos librerías se ha integrado: en vez de instalar un
paquete de terceros con su propio DOM y su propia gestión de foco (una caja negra
más difícil de auditar y de mantener alineada con el resto del sistema de diseño
Angular), el banner es un componente propio (`CookieBanner`) construido con los
mismos bloques (`app-button`, señales, `afterNextRender`) que el resto del panel,
lo que permite verificar directamente los criterios de abajo en vez de confiar en
la accesibilidad de una librería externa. Documentado aquí en vez de en el PRD
porque es una decisión de implementación, no de producto.

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 2.4.3 | Orden del foco | Al aparecer el banner, el foco se mueve al panel (`afterNextRender` + `.focus()`); al decidir (aceptar/rechazar/guardar), el foco vuelve al elemento que lo tenía antes de que apareciera el banner | ✅ |
| 2.1.2 | Sin trampa de foco | El banner no es un diálogo modal: no intercepta `Tab`/`Shift+Tab`, el resto de la página sigue siendo alcanzable mientras está visible | ✅ |
| 1.3.1 / 4.1.2 | Información y relaciones | `role="region"` con `aria-label`; casillas de categoría dentro de `fieldset`/`legend`; cada `label` envuelve su `input`, sin necesitar `id` generado | ✅ |
| 1.4.1 / — | Uso del color | "Aceptar todo" / "Rechazar todo" / "Personalizar" usan la misma variante de botón (`secundario`), verificado con un test que compara las clases CSS de los tres, no solo revisión visual | ✅ |
| 2.1.1 | Teclado | Las tres acciones y las casillas de personalizar son accesibles y activables por teclado (elementos `button`/`input` nativos, sin manejadores de solo ratón) | ✅ |
| 1.3.1 | Encabezados | Cada página legal pública tiene un único `h1` con el nombre de la página | ✅ |
| — | Cobertura automática | `cookie-banner.spec.ts`, `legal-page.spec.ts`, `legal-pages-page.spec.ts`: cero violaciones de axe en el banner (con y sin personalización visible), las cuatro páginas legales con contenido renderizado y el editor del panel | ✅ |

**Contenido legal sin `[innerHTML]` directo.** Las páginas legales muestran el
contenido primero como texto plano interpolado por Angular (SSR y antes de
hidratar) y solo lo sustituyen por HTML saneado (`marked` + `DOMPurify`, lista
blanca explícita) tras `afterNextRender` en el navegador — nunca hay una ventana
en la que un `<script>` guardado como contenido legal pudiera ejecutarse, ni en el
servidor ni en el cliente. Verificado con un test explícito que guarda
`<script>alert(1)</script>` como contenido y comprueba que no aparece como
etiqueta `<script>` real en el DOM servido (`legal-page.spec.ts`), además de un
test de la función de saneado en sí (`sanitize-markdown.spec.ts`) y uno en el
backend que confirma que el contenido viaja como string dentro de JSON, nunca
como HTML de la propia respuesta.

## Checklist manual — Fase 6 del PRD (pagos con Stripe Connect)

Revisado sobre las cinco pantallas nuevas: `/admin/organization` (conexión
Stripe, `stripe-connection.ts`), `/admin/events/:id` → tipos de entrada
(`event-ticket-types.ts`) y códigos de descuento (`event-discount-codes.ts`),
`/admin/events/:id` → pagos y reembolsos (`event-payments.ts`), el paso de
compra del formulario público (`registration-page.ts`) y la pantalla de
retorno de pago (`payment-return.ts`).

| # | Criterio WCAG 2.1 AA | Cómo se ha comprobado | Resultado |
|---|---|---|---|
| 4.1.3 | Mensajes de estado | El estado de la conexión Stripe (`stripe-connection.ts:47`) y el de la pantalla de retorno de pago (`payment-return.ts:47`) viven en un `<div aria-live="polite">`: un lector de pantalla anuncia el cambio de "conectando"/"pendiente" a "conectado"/"pagado" sin que la persona tenga que volver a enfocar nada | ✅ |
| 4.1.3 | Mensajes de estado | El mensaje de éxito/error tras reembolsar en `event-payments.ts:85` usa `role="status" aria-live="polite"`, mismo patrón que el resto de formularios del panel | ✅ |
| 4.1.2 | Nombre, función, valor | Los botones de reordenar tipos de entrada (`event-ticket-types.ts:80,88`) llevan `aria-label` con el nombre de la acción, mismo patrón ya usado por `sponsor-tiers-page` en la fase 5 | ✅ |
| 2.1.1 | Teclado | Los formularios de tipo de entrada, código de descuento y el paso de compra del formulario público usan controles nativos (`input`/`select`/`button`), sin manejadores de solo ratón | ✅ |
| 1.3.1 | Encabezados y estructura | Cada pantalla nueva del panel tiene un único `h1`/`h2` propio dentro de su tarjeta, sin saltarse niveles | ✅ |
| — | Cobertura automática | `stripe-connection.spec.ts`, `event-ticket-types.spec.ts`, `event-discount-codes.spec.ts`, `event-payments.spec.ts`, `registration-page.spec.ts` y `payment-return.spec.ts`: cero violaciones de axe en cada estado con datos (sin conectar/conectado/desautorizado, lista vacía/con tipos, con/sin código de descuento aplicado, pago pendiente/pagado/reembolsado) | ✅ |

**El paso de compra no introduce un widget de pago propio.** Con Checkout
hosted, la página de pago la aloja Stripe: el formulario público solo pide
tipo de entrada, código opcional y los datos ya existentes de inscripción, y
redirige. No hay ningún campo de tarjeta ni iframe de Stripe.js que auditar
en el frontend de este proyecto — el único punto de accesibilidad de pago
que corresponde a esta fase es antes (selección) y después (retorno) del
propio Checkout.

## Al añadir una pantalla

1. Externaliza todos los textos a `es-ES.json`.
2. Usa los componentes de `shared/ui`, que ya resuelven etiquetas, errores y foco.
3. Añade un test que llame a `esperarSinViolacionesDeAccesibilidad`.
4. Recorre la pantalla solo con teclado.
5. Añade la fila correspondiente al checklist de esta página.
