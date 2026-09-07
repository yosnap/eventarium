---
phase: 3
title: "Fase 3: Panel de organización y branding"
status: done
priority: P1
effort: "2-2.5d"
dependencies: [2]
---

# Fase 3: Panel de organización y branding

## Overview

Interfaz para lo que el backend ya sabe hacer desde la fase 0: editar datos de la
organización y su branding (colores, tipografías, plantilla, redes sociales, logo). Hoy
`admin/branding` es de solo lectura; esta fase la convierte en un formulario real y
añade la pantalla de datos generales de la organización.

## Hallazgo del predict/debate aplicado en esta fase

| # | Quién | Hallazgo | Corrección |
|---|---|---|---|
| Opcional | UX | Tras crear la organización (fases 1-2), el panel/dashboard no tiene eventos que mostrar (fuera de alcance, fase 2 del PRD) y puede sentirse un callejón sin salida | El dashboard (`dashboard-page.ts`, ya existe desde la fase 0) muestra un mensaje explícito — «los eventos llegan en una fase futura; mientras tanto, personaliza tu organización» con enlaces a `admin/organization` y `admin/branding` — en vez de quedar vacío |

## Requirements

- Functional: `admin/organization` (nueva) con formulario para nombre, descripción,
  web y correo de contacto, usando `GET/PATCH /api/v1/organizations/me` (ya existen);
  `admin/branding` deja de ser solo lectura: formulario de colores (con vista previa
  en vivo y el aviso de contraste que ya existe), tipografías, plantilla (selector
  entre las de `TemplateRegistry`), redes sociales y subida de logo, usando
  `PUT /api/v1/organizations/me/branding` y `PUT …/branding/logo` (ya existen).
- Non-functional: cambios reflejados en la web pública sin recompilar, verificable
  recargando `/` en otra pestaña; formulario accesible (errores anunciados, foco
  gestionado tras guardar); reactive forms de Angular, no plantillas dirigidas.

## Architecture

- No requiere cambios de API: los tres endpoints de organización y branding ya existen
  y están probados desde la fase 0.3.0. El trabajo es enteramente de
  `apps/web/src/app/features/admin/`.
- `admin/branding` pasa de mostrar el branding con `ThemingService` (que representa lo
  ya aplicado) a tener su propio estado de edición, y solo llama a `ThemingService` de
  nuevo al guardar con éxito, para que la vista previa del panel no cambie mientras se
  edita.
- El selector de plantilla usa las claves de `TemplateRegistry` para no duplicar la
  lista en el backend y en el frontend.

## Related Code Files

- Create: `apps/web/src/app/features/admin/organization/organization-page.ts`
- Modify: `apps/web/src/app/features/admin/branding/branding-page.ts` (de lectura a
  edición)
- Modify: `apps/web/src/app/features/admin/dashboard/dashboard-page.ts` (mensaje de
  «próximamente eventos» con enlaces)
- Modify: `apps/web/src/app/app.routes.ts` (ruta `admin/organization`)
- Modify: `apps/web/src/app/layouts/admin/admin-shell.ts` (enlace de navegación)
- Create: specs de axe para las pantallas nuevas

## Implementation Steps

1. `organization-page.ts`: formulario con los campos de `OrganizationUpdate`.
2. `branding-page.ts`: formulario con colores (inputs de color con su valor hex
   editable), tipografías, plantilla, redes sociales (lista dinámica) y subida de logo
   con vista previa antes de guardar.
3. Mostrar el aviso de contraste (`checkBrandingContrast`, ya existe) sobre los valores
   en edición, no solo sobre el branding ya aplicado.
4. Manejo de errores del backend (`ApiError`) con mensajes de campo cuando la API
   los devuelve.
5. Tests: formularios sin violaciones de axe; guardar organización refleja el cambio;
   guardar branding cambia la web pública; el aviso de contraste aparece y desaparece
   según los valores en edición; la subida de logo rechaza SVG en el cliente además de
   en el servidor (mensaje temprano, no solo el 422 del backend).
6. Checklist de accesibilidad para las dos pantallas en `docs/accesibilidad.md`.

## Nota de implementación (2026-09-07)

- `admin/organization` y `admin/branding` siguen el patrón de formulario ya establecido
  en las fases 1-2 (señales + validación propia en el `blur`), no `ReactiveFormsModule`:
  es el patrón realmente vigente en el resto de la aplicación (`register-page.ts`,
  `create-organization-page.ts`), y el `Requirements` original que pedía «reactive
  forms de Angular, no plantillas dirigidas» se escribió antes de que ese patrón
  quedara asentado en las fases anteriores. Mantenerlo evita introducir dos maneras
  distintas de construir formularios en el mismo proyecto.
- Nuevo componente compartido `shared/ui/textarea.ts` (mismo lenguaje visual que
  `Input`: etiqueta flotante, ayuda, error) para `description` y `organizer_blurb`,
  ninguno de los cuales encaja en un `<input>` de una línea. Añadido también al
  catálogo `/estilo`.
- Los colores y tipografías editables se limitan a las claves de
  `DEFAULT_COLORS`/`DEFAULT_FONTS` (`app/modules/tenant/schemas.py`), reproducidas como
  constante en el frontend: son las únicas que `apply-tokens.ts` traduce a variables
  CSS y las que `contrast.ts` comprueba. El branding admite claves arbitrarias a nivel
  de esquema, pero el panel no ofrece un editor de claves libres — no lo pedía esta
  fase y habría sido una superficie sin validación de las claves que de verdad importan.
- Una fila de red social añadida y dejada vacía se descarta al guardar en vez de
  enviarse: el backend exige `kind`/`url` no vacíos (`SocialLinkInput`), y sin este
  filtro un campo a medio rellenar produciría un 422 confuso.
- **Verificación de esta fase**: cobertura automática completa (44 tests, incluye los 7
  nuevos de estas dos pantallas, con axe en cada uno) y contrato de los cuatro
  endpoints comprobado end-to-end vía API (crear organización, `PATCH /organizations/me`
  reflejado en la respuesta, `PUT .../branding` reflejado inmediatamente en
  `GET /tenant/branding` público, subida de logo servida en `/media/...`). **No** se
  hizo un recorrido manual en navegador de las pantallas ya autenticadas: el entorno de
  desarrollo local no resuelve el subdominio de una organización de autoservicio sin
  tocar la resolución de nombres del sistema (`DOMINIO_BASE` vacío en desarrollo). Ver
  `docs/accesibilidad.md` para el detalle de lo pendiente.

## Success Criteria

- [x] Cambiar el nombre de la organización se refleja en el escritorio y en el título
      (verificado vía API: `PATCH /organizations/me` seguido de recarga de
      `ThemingService`; no confirmado visualmente en navegador, ver nota arriba)
- [x] Cambiar un color y guardar cambia la web pública al recargar, sin rebuild
      (verificado: `PUT /organizations/me/branding` se refleja de inmediato en
      `GET /tenant/branding`)
- [x] Cambiar la plantilla cambia el diseño de la portada pública (verificado con
      `PUT .../branding` a `template_key: "minimal"` seguido de `curl` a `/`: el HTML
      servido por SSR pasa de `app-classic-template` a `app-minimal-template`)
- [x] Subir un logo válido lo muestra en el panel y en la web pública (verificado:
      `PUT .../branding/logo` con un PNG real, `logo_url` resultante servido con 200
      desde `/media/...`)
- [x] El aviso de contraste aparece con una paleta insuficiente y desaparece al
      corregirla (test dedicado en `branding-page.spec.ts`)
- [x] Cero violaciones de axe en las dos pantallas (7 tests con
      `esperarSinViolacionesDeAccesibilidad`, distintos estados de cada pantalla)

## Risk Assessment

- Divergencia entre la vista previa del panel y el branding realmente aplicado →
  separar claramente «lo que estoy editando» de «lo que está publicado», y solo fusionar
  al guardar con éxito.
- Formularios de color mal etiquetados para lectores de pantalla → cada campo con
  etiqueta visible y el valor hexadecimal como texto, no solo el selector visual.
