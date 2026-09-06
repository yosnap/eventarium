# Contribuir a Eventarium

Gracias por querer aportar. Este documento explica cómo trabajamos.

Para levantar el entorno, lee [`docs/desarrollo.md`](docs/desarrollo.md).

## Flujo de ramas

```
feature → develop → main
```

- `main` es el estado publicado. **Solo se llega por pull request**, nunca con un push
  directo.
- `develop` integra el trabajo y es donde se valida antes de publicar.
- Cada fase o tarea tiene su rama, creada desde `develop`.

```
{tipo}/{versión}-{descripción}

feat/0.6.0-eventos-y-sesiones
fix/0.5.1-correccion-refresh
chore/0.5.2-actualizar-dependencias
```

Tipos: `feat`, `fix`, `chore`, `refactor`, `docs`.

```bash
git checkout develop && git pull
git checkout -b feat/0.6.0-eventos-y-sesiones
# … trabajo y commits …
git rebase develop
gh pr create --base develop
```

Los merges a `develop` se hacen con `--no-ff` para que cada rama siga siendo
identificable en el historial.

## Versionado

Versionado semántico. Cada fase del plan recibe su **versión menor**:

| Fase | Versión |
|---|---|
| Monorepo y entorno | 0.1.0 |
| Backend FastAPI base | 0.2.0 |
| Multi-tenant con RLS | 0.3.0 |
| Frontend y theming | 0.4.0 |
| Documentación y CI | 0.5.0 |

Las correcciones sobre una versión publicada suben el patch (`0.5.1`). La `1.0.0`
llegará cuando el producto cubra el alcance del PRD.

Al publicar: actualizar `apps/api/pyproject.toml` y `apps/web/package.json`, abrir el
PR de `develop` a `main` y, tras el merge, crear el tag `vX.Y.Z` y la release.

## Commits

Formato *Conventional Commits*, en español de España:

```
feat(auth): añadir rotación de refresh tokens
fix(rls): corregir la política de user_social_links
docs(despliegue): documentar el ciclo de restauración
```

Commits atómicos: un cambio, un commit. Explica **por qué**, no solo qué: el qué ya
está en el diff.

## Checklist de un pull request

- [ ] Los tests pasan: `make test`
- [ ] Lint y tipos pasan: `make lint`
- [ ] Sin violaciones de accesibilidad; si hay pantalla nueva, tiene su fila en
      [`docs/accesibilidad.md`](docs/accesibilidad.md)
- [ ] Si cambia la API, `make api-types` ejecutado y `openapi.json` incluido
- [ ] Si añades una tabla con `organization_id`, tiene su política RLS y un test de
      aislamiento
- [ ] Ningún fichero supera las 1000 líneas
- [ ] Sin secretos: `make audit` limpio
- [ ] Documentación actualizada si cambia el comportamiento, la configuración o los
      comandos

## Reglas que no se negocian

Vienen de una revisión adversarial del diseño y saltárselas rompe garantías del
producto, no solo el estilo:

1. **El rol de la API nunca tiene `BYPASSRLS`.** Lo que necesite saltarse el aislamiento
   usa `app_maintainer`, y solo desde el CLI, las migraciones o `modules/admin`.
2. **Toda tabla con `organization_id` lleva política RLS** con `ENABLE` y `FORCE`.
3. **Fail-closed.** Sin contexto no se ven filas; sin Redis, la autenticación devuelve
   503. Nunca se continúa «por si acaso».
4. **Nadie concede permisos que no posee**, ni se asigna el rol de propietario sin
   serlo, ni amplía sus propios permisos.
5. **Las subidas se validan por sus bytes**, no por la extensión. SVG está prohibido
   hasta que exista saneado.
6. **Ningún secreto en el repositorio ni dentro de una imagen.**
7. **WCAG 2.1 AA en toda la aplicación**, panel incluido. Cero violaciones de axe, del
   impacto que sean.

## Código de conducta

Trata a los demás con respeto. No se aceptan insultos, acoso ni comentarios
discriminatorios. Quien mantiene el proyecto puede retirar contribuciones o vetar
cuentas que incumplan esto.

Para reportar un problema de conducta o una vulnerabilidad de seguridad, escribe a
quien mantiene el repositorio en privado en lugar de abrir una incidencia pública.
