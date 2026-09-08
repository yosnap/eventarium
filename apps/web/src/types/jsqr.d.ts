/**
 * `jsqr` no publica sus propios tipos ni un paquete `@types/jsqr` (comprobado
 * en el registro de npm) — declaración mínima de lo que usa la app de
 * escaneo (fase 4 del PRD, fase 3 de trabajo).
 */
declare module 'jsqr' {
  export interface QRPoint {
    readonly x: number;
    readonly y: number;
  }

  export interface QRLocation {
    readonly topLeftCorner: QRPoint;
    readonly topRightCorner: QRPoint;
    readonly bottomLeftCorner: QRPoint;
    readonly bottomRightCorner: QRPoint;
  }

  export interface QRCode {
    readonly data: string;
    readonly location: QRLocation;
  }

  export interface Options {
    readonly inversionAttempts?: 'dontInvert' | 'onlyInvert' | 'attemptBoth' | 'invertFirst';
  }

  export default function jsQR(
    data: Uint8ClampedArray,
    width: number,
    height: number,
    options?: Options,
  ): QRCode | null;
}
