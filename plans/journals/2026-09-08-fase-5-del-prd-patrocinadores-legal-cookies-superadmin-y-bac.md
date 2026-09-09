---
title: "Fase 5 del PRD: patrocinadores, legal/cookies, superadmin y backups"
date: 2026-09-08
summary: "Implementación completa de las 5 fases de trabajo, code-review y ak:review-pr con hallazgos reales corregidos, merge a develop (PR #23) con CI en verde."
---

# Fase 5 del PRD: patrocinadores, legal/cookies, superadmin y backups

## Qué se hizo

Implementación completa de la Fase 5 del PRD (bloque M, MVP IAWIC Valencia):
niveles de patrocinio + patrocinadores por evento con bloque público agrupado
por nivel; banner de cookies propio (WCAG 2.1 AA) + páginas legales editables
con Markdown saneado (marked + DOMPurify) + registro anónimo de consentimiento;
superadmin con auditoría de acciones sensibles, exportación RGPD de eventos y
borrado de inscritos bajo solicitud (reutilizando el flujo de cancelación y
promoción de lista de espera); revalidación de `restore.sh` con modo de
restauración aislado, verificado contra el esquema ampliado (recuento de filas
+ verificación de objetos en bucket).

Las 5 fases de trabajo del plan (`plans/260908-1610-prd-fase-5-patrocinadores-legal-superadmin/`)
se delegaron secuencialmente a subagentes `fullstack-developer`, cada uno con
contexto acotado (paths exactos, requirements, success criteria del .md de su
fase). Migración `0012_patrocinio_legal_auditoria`, 367 tests backend + ~170
frontend, 0 violaciones axe.

## Decisiones tomadas durante la sesión

- **Banner de cookies propio en vez de Orejime/Klaro.** El plan pedía evaluar
  Orejime (con Klaro como fallback si fallaba WCAG). El agente de la fase 3
  construyó un componente de primera parte en su lugar, argumentando control
  directo sobre los criterios WCAG vía tests. Presentado al usuario y
  aprobado explícitamente — desviación documentada en `phase-03-*.md`.
- **Retirada de consentimiento de cookies añadida tras `ak:review-pr`.** La
  primera pasada de revisión encontró que no había forma de retirar/cambiar
  el consentimiento una vez dado (hallazgo I2, sin cobertura como no-objetivo
  en el plan). El usuario decidió añadirlo en el mismo PR en vez de diferirlo.
- **Estrategia de cierre: rama feature + PR + `ak:review-pr` + merge**, misma
  norma que fases anteriores del proyecto — el usuario lo confirmó
  explícitamente en vez de commitear directo a `develop`.

## Hallazgos reales corregidos

`ak:code-review` (high) sobre el diff completo: 10 hallazgos, incluidos 2
bugs funcionales reales (exportación RGPD rota por `GET` con body,
incompatible con la Fetch API del `HttpClient`; auditoría de cambio de
permisos que podía persistir tras un rollback de la transacción principal).
Todos corregidos con test de regresión.

`ak:review-pr` (primera pasada): veredicto "Request changes" — 1 crítico
(CI en rojo de verdad por lint/formato en 14 ficheros nuevos, mientras el
informe de la fase 5 afirmaba erróneamente "ruff/mypy limpios") y 2
importantes (retirada de consentimiento de cookies ausente; `restore.sh` en
modo aislado protegía la base de datos pero no el bucket de objetos —
riesgo real de sobrescribir el bucket de producción si se olvida una
variable de entorno). Los 3 corregidos, re-revisión con veredicto "Approve".
Deuda menor aceptada y documentada en `plan.md` (3 sugerencias no
bloqueantes).

## Incidente operativo

Un subagente ejecutó `dev.sh stop` durante su verificación manual y paró
todo el stack de desarrollo, incluida una sesión de `ng serve` que no había
iniciado él — causó un error de login real para el usuario a mitad de
sesión. Diagnosticado y resuelto reiniciando con `dev.sh all`. Instrucción
reforzada en los siguientes prompts de subagente: dejar el stack exactamente
como se encontró.

## Resultado

PR #23 mergeado a `develop` (squash, commit `4d6eb34`), CI post-merge en
verde tras un rerun (la primera ejecución se canceló sin causa de
concurrencia identificada — posible comportamiento transitorio de GitHub
Actions, resuelto con `gh run rerun`). Working tree local sincronizado con
`develop`, stack de desarrollo operativo.

## Próximos pasos

- Deuda documentada en `plan.md`: arreglo de una línea en `restore.sh`
  (guarda del bucket usa `-n` en vez de `-d`), desactivación de scripts al
  retirar consentimiento antes de conectar analítica real, botón redundante
  en primera visita del banner.
- Fase 6 del PRD (pagos con Stripe Connect) queda desbloqueada.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
