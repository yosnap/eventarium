/**
 * `BarcodeDetector` (Shape Detection API) todavía no está en `lib.dom.d.ts`
 * de TypeScript — declaración mínima de lo que usa la app de escaneo (fase 4
 * del PRD, fase 3 de trabajo). Soporte real: Chrome/Android; el resto cae al
 * respaldo con `jsqr` (decisión #10 del plan).
 */
interface BarcodeDetectorOptions {
  readonly formats?: readonly string[];
}

interface DetectedBarcode {
  readonly rawValue: string;
}

declare class BarcodeDetector {
  static getSupportedFormats(): Promise<string[]>;
  constructor(options?: BarcodeDetectorOptions);
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>;
}

interface Window {
  readonly BarcodeDetector?: typeof BarcodeDetector;
}
