// Script de ejemplo de categoría "analíticas", solo para probar de verdad el
// bloqueo del banner de cookies (fase 5 del PRD): no hace ningún seguimiento
// real, solo cuenta cuántas veces se ha cargado en esta pestaña. El día que
// se añada un script analítico real (ej. Plausible, Matomo), sustituye a
// este mismo punto de carga en `dummy-analytics.service.ts` — el bloqueo
// hasta consentimiento ya está resuelto.
(function () {
  window.__dummyAnalyticsHits = (window.__dummyAnalyticsHits || 0) + 1;
})();
