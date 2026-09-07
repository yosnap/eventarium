---
phase: 5
title: "Fase 5: Cuenta propia y cierre de fase"
status: pending
priority: P1
effort: "1.5-2d"
dependencies: [4]
---

# Fase 5: Cuenta propia y cierre de fase

## Overview

Lo que le falta a una persona para gestionar su propia cuenta (perfil, contraseña,
enlaces sociales, y el selector de organización si pertenece a varias), más el cierre
de la fase: documentación al día, checklist de accesibilidad completo y verificación de
extremo a extremo del flujo completo de registro.

## Decisión a validar antes de implementar

¿Puede una persona pertenecer a varias organizaciones? Si la respuesta de la fase 2
sigue siendo «sí» (opción por defecto propuesta en el plan), esta fase añade el
selector; si se decidió que no, esta fase se reduce a perfil y contraseña.

## Requirements

- Functional: `admin/account` con edición de nombre, correo (con nueva verificación si
  cambia), enlaces sociales (`user_social_links`, backend ya existe salvo el router,
  que se añade aquí), cambio de contraseña; si aplica, selector de organización en la
  cabecera del panel que navega al subdominio correspondiente.
- Non-functional: cambiar el correo exige repetir la verificación de la fase 1 antes de
  aplicarlo, para no perder la propiedad de la cuenta por un error de tecleo.

## Architecture

- Nuevo `modules/users/router.py` amplía `GET /users/me` (ya existe) con
  `PATCH /users/me`, `POST /users/me/change-password`, y CRUD de
  `user_social_links` bajo `/users/me/social-links`. Este último no tenía endpoints
  hasta ahora: el modelo existe desde la fase 0.3.0 pero sin router.
- El selector de organización (si aplica) es un componente en `admin-shell.ts` que
  lista las organizaciones del usuario (`organization_members` filtradas por
  `user_id`, necesita un endpoint nuevo `GET /users/me/organizations`) y navega
  cambiando de subdominio.

## Related Code Files

- Create: `apps/api/app/modules/users/router.py` (ampliar), `schemas.py`
- Create: `apps/api/tests/modules/test_users_account.py`
- Create: `apps/web/src/app/features/admin/account/account-page.ts`
- Modify: `apps/web/src/app/layouts/admin/admin-shell.ts` (selector, si aplica)

## Implementation Steps

1. Confirmar con el usuario si el selector de organización entra en esta fase.
2. Backend: `PATCH /users/me`, cambio de contraseña (exige la actual), CRUD de enlaces
   sociales, y `GET /users/me/organizations` si aplica.
3. Cambiar el correo reenvía verificación y no aplica el cambio hasta confirmarlo.
4. `account-page.ts` con los formularios correspondientes.
5. Selector de organización, si aplica.
6. Tests de API y de accesibilidad para todo lo anterior.
7. **Cierre de fase**: recorrer el checklist de `Success Criteria` del `plan.md`
   completo, no solo de esta fase de trabajo; actualizar `docs/arquitectura.md` y
   `docs/modelo-de-datos.md` con lo añadido (tablas de correo/verificación si
   corresponde, endpoints nuevos); completar `docs/accesibilidad.md`.
8. Verificación de extremo a extremo: una persona sin cuenta llega a registrarse,
   verifica, crea su organización, la personaliza, invita a alguien y esa persona
   completa su perfil — todo sin intervención manual en base de datos.

## Success Criteria

- [ ] Cambiar el correo exige verificar el nuevo antes de aplicarlo
- [ ] Cambiar la contraseña exige la actual
- [ ] Los enlaces sociales se gestionan desde el panel
- [ ] (Si aplica) el selector cambia de organización navegando al subdominio correcto
- [ ] El flujo de extremo a extremo del plan completo se ha ejecutado una vez y
      documentado, no solo declarado
- [ ] `docs/` refleja el estado real del código
- [ ] Cero violaciones de axe; checklist WCAG de la fase 1 del PRD completo

## Risk Assessment

- Permitir cambiar el correo sin reverificar dejaría una cuenta huérfana si se teclea
  mal → verificación obligatoria del correo nuevo antes de aplicar el cambio.
- Cerrar la fase sin la verificación de extremo a extremo repetiría el patrón de la
  fase 0, donde varios fallos reales pasaban con CI en verde → paso explícito de
  verificación manual antes de dar la fase por cerrada.
