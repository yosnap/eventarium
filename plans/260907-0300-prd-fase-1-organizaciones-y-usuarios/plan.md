---
title: "PRD Fase 1 — Organizaciones y usuarios"
description: "Registro libre de organizadores con subdominio automático, panel de organización, branding editable, roles con campos de perfil, miembros y cuenta propia. Primera funcionalidad de negocio sobre los cimientos de la fase 0."
status: pending
priority: P1
effort: "8-12d"
tags: [registro, organizaciones, branding, roles, miembros, email]
created: 2026-09-07
prd_phase: 1
blockedBy: []
blocks: []
---

# PRD Fase 1 — Organizaciones y usuarios

## Nomenclatura

Este plan cubre la **fase 1 del PRD** (`docs/prd.md` §9). Dentro se subdivide en cinco
fases de trabajo numeradas 1-5, cada una con su versión menor y su rama.

Se adopta el prefijo `prd-fase-N` en el nombre del directorio porque la fase 0 generó
confusión: sus cinco fases internas se leían como fases del producto. **Fase del PRD** es
el producto; **fase de trabajo** es un tramo dentro de este plan.

## Overview

La fase 0 dejó los cimientos: multi-tenant con RLS, autenticación, almacenamiento,
tareas asíncronas, theming por organización y CI. El backend de organizaciones, roles y
miembros existe y está probado, pero **no hay interfaz que lo use** y **no hay forma de
darse de alta**: hoy solo un superadministrador crea organizaciones por CLI o API.

Esta fase convierte eso en un producto usable: cualquiera se registra, crea su
organización, obtiene su subdominio y administra su equipo desde el panel.

Fuentes: `docs/prd.md` §3-4 y §9 (fase 1), `docs/arquitectura.md`, y las decisiones de
producto tomadas el 2026-09-07 (ver «Decisiones nuevas»).

## Decisiones nuevas (no estaban en el PRD)

El PRD describe la inscripción de **asistentes**, no el alta de **organizadores**. Esto
se decidió el 2026-09-07 y se incorpora aquí:

| Decisión | Detalle |
|---|---|
| Registro libre | Cualquiera crea una cuenta y una organización desde la web, sin intervención del superadministrador |
| Un subdominio por organización | `mi-org.dominio-de-la-instalacion` registrado automáticamente al crear la organización |
| Dominio propio | Fuera de alcance: quien lo quiera hace fork y despliega su instalación (fase 8 del PRD para el caso general) |
| Proxy en producción | EasyPanel (Traefik). Caddy queda solo para desarrollo |

## Dependencia que adelanta trabajo

El registro necesita **verificar el correo**, y eso exige infraestructura de envío que el
PRD situaba en la fase 3. Se adelanta a la fase de trabajo 1 de este plan.

No es un adelanto gratuito: sin verificación, cualquiera crearía organizaciones con
correos ajenos y ocuparía subdominios. La alternativa —permitir crear sin verificar—
dejaría basura en la tabla de organizaciones y subdominios secuestrados, que es
justamente lo que el subdominio automático vuelve valioso para un atacante.

## Fases de trabajo

| # | Fase | Versión | Rama | Estado |
|---|---|---|---|---|
| 1 | [Correo y verificación](./phase-01-correo-y-verificacion.md) | 0.7.0 | `feat/0.7.0-correo-y-verificacion` | Pending |
| 2 | [Registro y alta de organización](./phase-02-registro-y-alta-de-organizacion.md) | 0.8.0 | `feat/0.8.0-registro-y-alta-de-organizacion` | Pending |
| 3 | [Panel de organización y branding](./phase-03-panel-de-organizacion-y-branding.md) | 0.9.0 | `feat/0.9.0-panel-de-organizacion-y-branding` | Pending |
| 4 | [Roles, campos de perfil y miembros](./phase-04-roles-campos-y-miembros.md) | 0.10.0 | `feat/0.10.0-roles-campos-y-miembros` | Pending |
| 5 | [Cuenta propia y cierre de fase](./phase-05-cuenta-propia-y-cierre.md) | 0.11.0 | `feat/0.11.0-cuenta-propia-y-cierre` | Pending |

Dependencias: **estrictamente secuencial** 1 → 2 → 3 → 4 → 5. La 2 necesita el correo de
la 1; la 3, una organización creada por la 2; la 4, el panel de la 3.

## Protocolo de rama, revisión y merge

Se aplica a cada fase de trabajo, sin excepciones. El detalle vive en
[`CONTRIBUTING.md`](../../CONTRIBUTING.md); aquí queda el resumen operativo:

```
develop → feat/X.Y.0-nombre → (trabajo) → PR a develop → merge --no-ff
```

1. **Rama desde `develop`** actualizado, con el nombre de la tabla de arriba.
2. **Commits atómicos** en formato *Conventional Commits*, en español de España.
3. **Antes de abrir el PR**, en local y en verde:
   - `make lint` (ruff, mypy --strict, ESLint, Prettier)
   - `make test` (pytest contra servicios reales, Vitest con axe)
   - `make audit` (pip-audit, pnpm audit, gitleaks)
   - Si cambió la API: `make api-types` y el `openapi.json` incluido en el commit
4. **PR a `develop`** con: qué entra, por qué, y **cómo se ha verificado** — evidencia
   concreta, no «funciona». Si algo quedó sin verificar, se dice.
5. **Revisión antes del merge**: CI en verde en los tres jobs *y* revisión del diff con
   el checklist de PR de `CONTRIBUTING.md`. Un CI verde no sustituye a leer el cambio:
   en la fase 0, tres fallos reales (SSR degradado a cliente, worker que no arrancaba,
   restauración que rompía las migraciones) devolvían códigos de éxito.
6. **Merge `--no-ff`** a `develop` y actualización del estado de la fase en este plan.
7. **`main` solo por pull request**, nunca por push directo. La rama está protegida.

### Versionado

Cada fase de trabajo sube una **versión menor** en `apps/api/pyproject.toml` y
`apps/web/package.json`. Las correcciones sobre una versión ya publicada suben el patch.
El release a `main` con su tag `vX.Y.Z` se hace al cerrar cada fase o agrupando varias,
según convenga; el tag apunta siempre a un commit de `main`.

## Goals

| # | Goal | Prioridad |
|---|------|-----------|
| 1 | Cualquiera se registra, verifica su correo y crea su organización sin intervención manual | P1 |
| 2 | Cada organización queda servida en su propio subdominio desde el minuto uno | P1 |
| 3 | El panel permite editar organización, branding y plantilla, y ver el resultado | P1 |
| 4 | Los roles y sus campos de perfil se gestionan desde la interfaz, respetando las reglas anti-escalada | P1 |
| 5 | Se invita a personas al equipo y estas completan su perfil según su rol | P1 |
| 6 | Todo lo anterior cumple WCAG 2.1 AA y no rompe el aislamiento entre organizaciones | P1 |

## Non-goals

Eventos, sesiones y agenda (fase 2 del PRD); inscripciones (fase 3); entradas y QR
(fase 4); patrocinadores, pagos y contabilidad (fases 5-7); dominio propio por
organización (fase 8); inglés y otros idiomas (fase 8).

Tampoco entra la interfaz de superadministración: sigue siendo CLI y endpoints, como
en la fase 0.

## Success Criteria

- [ ] Una persona ajena al proyecto se registra, verifica el correo, crea su
      organización y llega a su panel sin ayuda ni intervención en base de datos
- [ ] La organización creada responde en su subdominio con su propio branding
- [ ] Un correo no verificado no puede crear organización
- [ ] Dos organizaciones creadas por personas distintas no se ven entre sí: los tests de
      aislamiento siguen en verde y se amplían a las tablas nuevas
- [ ] No se puede reclamar un subdominio ya usado ni uno de la lista de reservados
- [ ] El branding editado desde el panel se refleja en la web pública sin recompilar
- [ ] Un rol a medida con campos propios se crea, se asigna y sus campos se piden al dar
      de alta a alguien con ese rol
- [ ] Las reglas anti-escalada siguen cubiertas por tests y se aplican también en la UI
- [ ] Cero violaciones de axe en las pantallas nuevas; checklist WCAG completado
- [ ] CI en verde; ningún fichero supera las 1000 líneas
- [ ] `docs/` actualizado: arquitectura, modelo de datos y desarrollo reflejan lo nuevo

## Decisiones tomadas — Sesión de validación 2026-09-07

| # | Pregunta | Decisión |
|---|---|---|
| 1 | Proveedor de correo en desarrollo | Mailpit en `infra/docker-compose.yml`, sin salir a Internet |
| 2 | Turnstile en el registro | Sí, obligatorio en producción, desactivable por variable en desarrollo y tests |
| 3 | Elección de subdominio | El usuario lo elige; se sugiere a partir del nombre y se comprueba disponibilidad en vivo |
| 4 | Varias organizaciones por persona | Sí; el panel muestra un selector cuando la persona pertenece a más de una |
| 5 | Política de contraseñas | Mínimo 8 caracteres, comprobadas contra una lista de las más filtradas (k-anonymity, sin enviar la contraseña en claro) |
| 6 | Organización creada y nunca verificada | Correo de aviso a los 5 días; se borra a los 7 días por tarea programada, liberando el subdominio |

Sin contradicciones con las decisiones de la fase 0 (verificado: EasyPanel, subdominio
por organización, `TRUSTED_PROXY_CIDRS`, cookie first-party sin `Domain` — ninguna
choca con lo decidido aquí).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El subdominio automático convierte el registro en una vía de ocupación de nombres | Verificación de correo obligatoria antes de crear, lista de reservados, límite por IP y caducidad de las no verificadas |
| Adelantar el correo arrastra alcance de la fase 3 | Se implementa solo lo necesario para verificar: proveedor, plantilla y cola. Las plantillas de inscripción siguen en su fase |
| El envío de correo falla y bloquea el registro | La cola reintenta; la interfaz permite reenviar el enlace; el registro no se pierde si el correo tarda |
| La UI abre caminos que saltan las reglas anti-escalada | Las reglas viven en el servicio, no en la interfaz; se añaden tests de API por cada regla que la UI exponga |
| Varias organizaciones por persona complican el contexto de RLS | El contexto sigue viniendo del host, no de la sesión; el selector cambia de subdominio, no de variable |
