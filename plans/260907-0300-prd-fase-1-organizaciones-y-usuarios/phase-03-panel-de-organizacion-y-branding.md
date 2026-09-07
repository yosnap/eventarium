---
phase: 3
title: "Fase 3: Panel de organización y branding"
status: pending
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

## Success Criteria

- [ ] Cambiar el nombre de la organización se refleja en el escritorio y en el título
- [ ] Cambiar un color y guardar cambia la web pública al recargar, sin rebuild
- [ ] Cambiar la plantilla cambia el diseño de la portada pública
- [ ] Subir un logo válido lo muestra en el panel y en la web pública
- [ ] El aviso de contraste aparece con una paleta insuficiente y desaparece al
      corregirla
- [ ] Cero violaciones de axe en las dos pantallas

## Risk Assessment

- Divergencia entre la vista previa del panel y el branding realmente aplicado →
  separar claramente «lo que estoy editando» de «lo que está publicado», y solo fusionar
  al guardar con éxito.
- Formularios de color mal etiquetados para lectores de pantalla → cada campo con
  etiqueta visible y el valor hexadecimal como texto, no solo el selector visual.
