---
phase: 4
title: "Fase 4: Roles, campos de perfil y miembros"
status: done
priority: P1
effort: "2.5-3d"
dependencies: [3]
---

# Fase 4: Roles, campos de perfil y miembros

## Overview

Interfaz para gestionar roles (del sistema y a medida), sus campos de perfil, y el
equipo de la organización. El backend completo ya existe desde la fase 0.3.0, con sus
reglas anti-escalada y sus tests: aquí se expone sin abrir ninguna vía que las salte.

## Hallazgo del predict/debate aplicado en esta fase

| # | Quién | Hallazgo | Corrección |
|---|---|---|---|
| Opcional | Accesibilidad | Sin patrón de resumen de errores para formularios con varios fallos simultáneos (contraseña filtrada, slug reservado, campos obligatorios) — solo error inline no cumple bien WCAG 3.3.1/4.1.3 cuando hay varios a la vez | `dynamic-field.ts` y los formularios que lo usan (`role-form.ts`, `member-form.ts`) muestran, además del error inline, un resumen enlazado a cada campo cuando hay más de un error |

## Requirements

- Functional: `admin/roles` (lista con badge de rol del sistema vs a medida), crear rol
  a medida o desde plantilla, editar permisos y campos (respetando los bloqueados),
  borrar rol a medida; `admin/members` (lista paginada), invitar miembro por correo con
  rol y `profile_data` según los campos de ese rol (formulario dinámico generado desde
  `role_profile_fields`).
- Non-functional: el formulario de permisos solo muestra los permisos que el actor
  posee (la API los rechazaría igualmente, pero mostrarlos habilitados sin poder
  concederlos es mala experiencia); el formulario de campos dinámicos reutiliza los
  tipos ya definidos en el backend (`text`, `textarea`, `url`, `email`, `phone`,
  `date`, `select`, `boolean`) con su validación replicada en el cliente para dar
  error antes de enviar, sin sustituir la validación del servidor.

## Architecture

- `admin/roles`: lista desde `GET /api/v1/roles`; formulario de creación/edición contra
  `POST`/`PATCH /api/v1/roles/{id}`; borrado contra `DELETE`. El componente de campo
  dinámico (`shared/ui/dynamic-field.ts`, nuevo) mapea `field_type` a un control
  concreto y se reutiliza en `admin/members` para el alta.
- `admin/members`: lista desde `GET /api/v1/organizations/me/members`; alta contra
  `POST`; el selector de rol determina qué campos dinámicos se muestran, recargando la
  definición de campos de ese rol.
- Sin invitación por correo real en esta fase (el PRD la sitúa fuera del alcance
  descrito para miembros de equipo): el alta crea el usuario y la membresía
  directamente, como ya hace `members_service.add_member`. Si el usuario decide que
  hace falta invitación por correo aquí, es una decisión nueva a validar antes de
  implementar, no asumida por este plan.

## Related Code Files

- Create: `apps/web/src/app/features/admin/roles/{roles-page,role-form}.ts`
- Create: `apps/web/src/app/features/admin/members/{members-page,member-form}.ts`
- Create: `apps/web/src/app/shared/ui/dynamic-field.ts`
- Modify: `apps/web/src/app/app.routes.ts`, `admin-shell.ts`

## Implementation Steps

1. `dynamic-field.ts`: un control por `field_type`, con las mismas reglas de validación
   que `shared/dynamic_fields.py` (mínimo: requerido, formato de email/URL/teléfono,
   fecha ISO, opciones de `select`).
2. `roles-page.ts`: lista, con acciones deshabilitadas (no ocultas, para que quede claro
   por qué) cuando el usuario no tiene permiso.
3. `role-form.ts`: crear desde cero o desde plantilla; edición respeta `is_locked` en
   los campos, mostrándolos pero sin permitir borrarlos.
4. `members-page.ts` y `member-form.ts`: alta con campos dinámicos según el rol elegido.
5. Resumen de errores enlazado a cada campo en ambos formularios cuando hay más de un
   error a la vez.
6. Tests: formularios sin violaciones de axe; crear rol con permisos no poseídos no es
   ni siquiera ofrecido en la UI (y si se fuerza por API, ya está cubierto por los
   tests de la fase 0); borrar un rol del sistema muestra el 409 de forma legible; el
   formulario de miembro cambia sus campos al cambiar el rol seleccionado; el resumen
   de errores aparece con varios fallos simultáneos y cada entrada enlaza al campo.
7. Checklist de accesibilidad para las cuatro pantallas nuevas.

## Nota de implementación (2026-09-07)

- **Permisos que el actor no posee**: el `Requirements` de esta fase pedía «el
  formulario de permisos solo muestra los permisos que el actor posee», pero el
  `Risk Assessment` pedía lo contrario («mostrar permisos que el actor no posee como
  deshabilitados sin explicar por qué → añadir el motivo en un `title`»). Se resolvió
  a favor de mostrar **todos** los permisos, deshabilitando los que el actor no tiene
  con el motivo en `title` — ocultar una opción sin explicar por qué es más confuso
  que verla deshabilitada, y la API los rechazaría igual si se forzaran.
- **«Empezar desde plantilla»** no llama a ningún endpoint nuevo: los cinco roles del
  sistema ya están clonados en la organización desde que se creó (fase 2), así que sus
  permisos y campos ya vienen en la misma respuesta de `GET /roles` que alimenta el
  listado. Elegir una plantilla solo rellena el formulario con esos valores como vista
  previa — la fusión real la sigue haciendo `from_template` en el `POST`.
- **Campos bloqueados en la vista previa de plantilla**: `create_role` nunca bloquea
  campos en un rol nuevo (`_añadir_campos(..., bloqueados=False)`), aunque el rol del
  sistema del que se copian sí los tenga bloqueados. La vista previa del cliente
  fuerza `bloqueado: false` en los campos copiados desde una plantilla — verificado
  contra la API real: crear un rol desde la plantilla «Voluntariado» devuelve sus tres
  campos con `is_locked: false`, no `true`.
- **Fallo real encontrado y corregido durante la verificación manual** (no solo en las
  pruebas automáticas): pasar `[id]="…"` a `app-input`/`app-textarea` también fijaba
  ese `id` como atributo nativo en el elemento anfitrión del componente, duplicando el
  `id` en el DOM (una vez en `<app-input id="…">`, otra en su `<input id="…">`
  interno) — el resumen de errores enlazaba entonces al elemento equivocado. El
  `input` se renombró a `fieldId` en los tres componentes (`Input`, `Textarea`,
  `DynamicField`) para evitar la colisión con el atributo global `id`.
- **Segundo fallo real encontrado**: los `<select>` nativos cuyo valor se fija desde
  una respuesta de la API (no desde la propia interacción de la persona) mostraban
  visualmente la primera opción de la lista en vez de la correspondiente, aunque el
  dato interno fuera correcto — un `[value]` en el `<select>` no garantiza que el
  navegador lo aplique si las `<option>` generadas por `@for` aún no existen en ese
  ciclo. Corregido con `[selected]` por opción en los cuatro selectores afectados
  (tipo de campo y plantilla en `role-form.ts`, plantilla en `branding-page.ts`,
  selector en `dynamic-field.ts`).

## Success Criteria

- [x] Crear un rol a medida con campos propios, asignarlo a alguien y ver esos campos
      pedidos en el alta (verificado contra la API real: rol «Ponente» con `bio`
      obligatoria, alta de miembro con `profile_data` validado)
- [x] Editar un rol del sistema: se pueden añadir campos, no borrar los bloqueados
      (`update_role` rechaza con 409 si falta un campo bloqueado; cubierto por los
      tests de la fase 0, no repetido aquí)
- [x] Borrar un rol del sistema muestra el error de forma legible, no una excepción
      (verificado: 409 con `detail` legible, mostrado en la alerta de la página)
- [x] La lista de miembros muestra rol y datos de perfil
- [x] Ningún control de permisos que el actor no posee aparece habilitado (verificado
      con un actor con 3 de los 8 permisos: los otros 5 quedan deshabilitados)
- [x] Cero violaciones de axe

## Risk Assessment

- Duplicar la validación de campos dinámicos entre cliente y servidor puede
  desincronizarse → un único fichero de reglas de validación, compartido si el
  proyecto migra a un monorepo de tipos, o al menos con comentario cruzado señalando el
  origen en `shared/dynamic_fields.py`.
- Mostrar permisos que el actor no posee como deshabilitados sin explicar por qué →
  añadir el motivo en un `title` o texto de ayuda.
