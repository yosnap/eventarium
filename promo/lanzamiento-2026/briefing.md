# Briefing: lanzamiento-2026 (Eventarium)

**Prompt del dueño (resumen, 2026-10-01):** vídeo promocional de Eventarium que enseñe lo que pueden hacer
las organizaciones: eventos y plantillas, ponentes, tipos de evento e inscripción, asistentes con QR,
control de gastos, políticas y páginas legales propias; web como superficie 3D con cursor pulsando botones.

| Campo | Valor | Origen |
|---|---|---|
| Destino | YouTube 16:9 (después, corte vertical hermano) | dueño |
| Duración | 70-100 s | dueño (90 s) |
| Público y objetivo | Organizadores de eventos → crear cuenta | dueño |
| Llamada a la acción | «Crea tu cuenta gratis en eventarium.org» | dueño |
| Estilo | superficie-3d, cursor con clic | dueño |
| Voz | **Esta versión: sin voz** (títulos en cada pantalla). Con voz: ElevenLabs «Martin Osborne 5» cuando la clave esté rotada | dueño |
| Música | Suave, 104 BPM, La menor (cuando el motor tenga audio) | dueño |
| Subtítulos | No (horizontal) | dueño |
| «Próximamente» / open source | Pendiente de decidir; fuera de esta versión | abierto |

## Datos de demostración

Organización ficticia «Cumbre Digital Valencia» (`cumbre-digital`), sembrada por
`apps/api/scripts/seed_video_promocional.py` (eventos del catálogo de demo + inscritos y contabilidad del
evento estrella). Propietaria `laura.martin.video@example.com`; su clave es `EVENTARIUM_VIDEO_CLAVE` en
`~/.config/fabrica-videos/env`. Las rutas del panel llevan el id del evento estrella de la base local;
si se recrea la base, hay que actualizar `capturas.json`.
