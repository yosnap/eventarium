# Servidor MCP

Eventarium expone un servidor [MCP](https://modelcontextprotocol.io) para que
un asistente (Claude, ChatGPT, Cursor, n8n…) trabaje con los eventos de una
organización en nombre de una persona: leerlos, prepararlos en borrador,
publicarlos o cancelarlos y consultar cifras de inscripción. Nunca ve datos
personales de asistentes.

- **URL**: `https://eventarium.org/mcp` (en local, `http://localhost:8080/mcp`).
- **Transporte**: Streamable HTTP sin estado, respuestas JSON.
- **Credenciales**: OAuth 2.1 (lo normal en asistentes) o clave de API
  (`evtm_…`, para scripts y automatizaciones).

## Quién puede conectarse

Hace falta el permiso **«Conectar asistentes por MCP»** (`mcp:connect`). Lo
tiene el dueño de la organización y es él quien lo asigna a otros roles en
*Roles*. Una conexión nunca da más de lo que la persona puede hacer en la web:
en cada llamada se recalculan los ámbitos como *concedidos ∩ rol actual*, así
que quitar un rol o el permiso corta la siguiente llamada.

## Ámbitos

| Ámbito | Permite | Exige en el rol |
|---|---|---|
| `eventos:leer` | Listar y ver eventos | `events:read` |
| `inscripciones:cifras` | Totales de inscripción y aforo, sin personas | `registrations:read` |
| `eventos:editar` | Crear eventos (siempre en borrador), editar ficha, sesiones y sedes | `events:write` |
| `eventos:publicar` | Publicar y despublicar | `events:write` |
| `patrocinadores:editar` | Añadir y editar patrocinadores | `sponsors:write` |
| `eventos:cancelar` | Cancelar un evento (definitivo, reembolsa) | `events:write` y, con cobros, `payments:write` |

Por defecto solo se marcan `eventos:leer` e `inscripciones:cifras`;
`eventos:cancelar` nunca viene marcado. La conexión puede limitarse a unos
eventos concretos; en ese caso no puede crear eventos nuevos.

## Herramientas

- Lectura: `listar_eventos`, `ver_evento`, `cifras_de_inscripcion`,
  `listar_niveles_de_patrocinio`.
- Escritura: `crear_evento`, `editar_evento`, `anadir_sesion`,
  `editar_sesion`, `quitar_sesion`, `anadir_sede`, `anadir_patrocinador`,
  `editar_patrocinador`.
- Estado: `publicar_evento`, `despublicar_evento` (se niega si hay
  inscripciones vivas) y `cancelar_evento`.

`cancelar_evento` va en dos pasos: la primera llamada devuelve un resumen
(inscripciones y cobros afectados) y un código de confirmación válido unos
minutos; solo la segunda, con ese código, cancela. Cada escritura queda en el
registro de auditoría con la conexión que la hizo, igual que las de la web.

## Conectar un asistente (OAuth)

1. En el asistente, añade un conector o servidor MCP remoto con la URL
   `https://eventarium.org/mcp`.
   - **Claude**: *Ajustes → Conectores → Añadir conector personalizado*.
   - **ChatGPT**: *Ajustes → Aplicaciones → Modo desarrollador → Crear*.
   - **Cursor**: en `mcp.json`, `{"mcpServers": {"eventarium": {"url": "https://eventarium.org/mcp"}}}`.
2. El asistente abre Eventarium. Inicia sesión si hace falta.
3. En la pantalla de consentimiento comprueba quién lo pide y adónde volverá
   (un cliente «no verificado» se ha registrado solo y su nombre lo pone él),
   elige ámbitos y eventos y pulsa **Permitir**. Solo se ofrecen los ámbitos
   que el asistente ha pedido y que tu rol permite.

La conexión dura 90 días. El asistente renueva sus tokens solo; si alguien
reutiliza un token de renovación ya usado, la conexión se revoca entera.

## Clave de API

En *Panel → Asistentes (MCP) → Nueva clave de API* se eligen nombre, ámbitos y
eventos. La clave se muestra **una sola vez** y caduca a los 90 días. Se envía
como cabecera:

```bash
curl -X POST https://eventarium.org/mcp \
  -H "Authorization: Bearer $EVENTARIUM_MCP_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Revocar

- Cada persona ve y revoca sus conexiones en *Panel → Asistentes (MCP)*, con
  el historial de lo que ha hecho cada una.
- El dueño ve y revoca las de todos los miembros de la organización.
- Cambiar la contraseña o el correo, restablecerla o desactivar la cuenta
  revoca todas las conexiones de la persona.

## Límites

120 llamadas por minuto por conexión y 600 por IP. Al pasarse, la herramienta
devuelve un error y el asistente debe esperar.

## Detalles técnicos

- Código en `apps/api/app/modules/mcp/` (herramientas, verificación, ámbitos)
  y `mcp/oauth/` (servidor de autorización). Tablas `mcp_connections` y
  `mcp_oauth_clients`, migraciones 0055 y 0056.
- El emisor OAuth es `…/mcp/oauth`. Metadatos RFC 9728 en
  `/.well-known/oauth-protected-resource/mcp` y RFC 8414 en
  `/.well-known/oauth-authorization-server/mcp/oauth`.
- Clientes por CIMD (el `client_id` es una URL; se descarga con protección
  SSRF) o por registro dinámico. PKCE S256 obligatorio.
- Los tokens de acceso son JWT de 15 minutos con `type=mcp_access`,
  audiencia = URL del MCP y un secreto propio (`MCP_JWT_SECRET`, derivado de
  `JWT_SECRET` si falta). No sirven en la API web ni al revés.
- El secreto de un cliente dinámico confidencial no se guarda: es un HMAC de
  su `client_id` con ese mismo secreto. Rotar `MCP_JWT_SECRET` (o
  `JWT_SECRET` si aquel está vacío) invalida los tokens y obliga a esos
  clientes a registrarse de nuevo.
- El proxy debe mandar `/mcp*` y `/.well-known/oauth-*` a la API sin
  bufferizar (`infra/caddy/Caddyfile`).
