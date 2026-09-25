import { defineConfig } from '@playwright/test';

/**
 * Pruebas e2e contra el entorno de desarrollo ya levantado (`make dev`):
 * frontend en 4200 con su proxy a la API, Mailpit en 8025 y los datos de
 * `make db-seed`. No arranca servidores propios: los del proyecto ya tienen
 * puerto fijo y duplicarlos dejaría procesos huérfanos.
 */
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:4200',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      // Android de gama media: el ancho más estrecho que hay que soportar.
      name: 'movil-360',
      use: {
        viewport: { width: 360, height: 780 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
        userAgent:
          'Mozilla/5.0 (Linux; Android 14; SM-A156B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36',
      },
    },
  ],
});
