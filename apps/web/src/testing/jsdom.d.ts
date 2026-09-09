/**
 * `jsdom` no publica sus propios tipos ni hay `@types/jsdom` instalado. Solo lo usa
 * `apply-tokens.spec.ts` para crear un documento aislado del `document` global de la
 * suite en el test de cascada; una declaración ambiental basta, no se necesita el tipado
 * completo del paquete.
 */
declare module 'jsdom';
