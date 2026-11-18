import {
  ApplicationConfig,
  LOCALE_ID,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import {
  provideRouter,
  withComponentInputBinding,
  withInMemoryScrolling,
  withRouterConfig,
  NavigationEnd,
  Router,
} from '@angular/router';
import { filter } from 'rxjs';
import { provideServiceWorker } from '@angular/service-worker';
import { TranslocoService, provideTransloco } from '@jsverse/transloco';

import { authInterceptor } from './core/api/auth.interceptor';
import { errorInterceptor } from './core/api/error.interceptor';
import { registrarDatosDeIdioma } from './core/i18n/datos-de-idioma';
import { IDIOMAS, IDIOMA_POR_DEFECTO } from './core/i18n/idioma';
import { idiomaInterceptor } from './core/i18n/idioma.interceptor';
import { IDIOMA, IdiomaService } from './core/i18n/idioma.service';
import { TraduccionesLoader } from './core/i18n/transloco-loader';
import { ThemingService } from './core/theming/theming.service';
import { environment } from '../environments/environment';
import { routes } from './app.routes';

registrarDatosDeIdioma();

export const appConfig: ApplicationConfig = {
  providers: [
    // El idioma de la visita (prefijo de la URL o, en los paneles, el de la cuenta).
    { provide: LOCALE_ID, useFactory: () => inject(IDIOMA) },
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    // Sin esto, un `routerLink` con `fragment` (p. ej. la miga de pan
    // "Programa" enlazando a `#agenda-h2`) cambia la URL pero no hace scroll:
    // Angular no activa el desplazamiento a anclas por defecto.
    provideRouter(
      routes,
      withComponentInputBinding(),
      withInMemoryScrolling({ anchorScrolling: 'enabled', scrollPositionRestoration: 'enabled' }),
      // Sin esto, un hijo de `events/:eventId` (p. ej. `agenda`) no ve el
      // `eventId` del padre: por defecto el router solo hereda parámetros de
      // rutas con `path: ''`, no de cualquier ruta con hijos (`EventShell`).
      withRouterConfig({ paramsInheritanceStrategy: 'always' }),
    ),
    provideClientHydration(withEventReplay()),
    // `withFetch` es necesario para que las peticiones funcionen igual en SSR.
    provideHttpClient(
      withFetch(),
      withInterceptors([errorInterceptor, idiomaInterceptor, authInterceptor]),
    ),
    provideTransloco({
      config: {
        availableLangs: [...IDIOMAS],
        defaultLang: IDIOMA_POR_DEFECTO,
        // Una clave sin traducir en otro idioma se muestra en español, nunca vacía.
        fallbackLang: IDIOMA_POR_DEFECTO,
        missingHandler: { useFallbackTranslation: true },
        reRenderOnLangChange: false,
        prodMode: true,
      },
      loader: TraduccionesLoader,
    }),
    // El branding se carga antes de pintar nada: así no hay un parpadeo con la paleta
    // por defecto antes de aplicar la de la organización.
    provideAppInitializer(() => inject(ThemingService).load()),
    // Idioma activo de Transloco y `<html lang>`, antes del primer pintado y
    // también en SSR, para que el HTML servido ya declare su idioma.
    provideAppInitializer(() => {
      const idioma = inject(IDIOMA);
      inject(TranslocoService).setActiveLang(idioma);
      inject(DOCUMENT).documentElement.lang = idioma;
      // Al cruzar entre panel y páginas públicas puede cambiar el idioma que toca.
      const servicio = inject(IdiomaService);
      inject(Router)
        .events.pipe(filter((evento) => evento instanceof NavigationEnd))
        .subscribe((evento) => servicio.recargarSiCambiaElIdioma(evento.urlAfterRedirects));
    }),
    // Solo la PWA de check-in (fase 4 del PRD) lo necesita hoy, pero registrarlo aquí
    // no afecta al resto del panel: `enabled` ya lo desactiva fuera de producción, y
    // `provideServiceWorker` no hace nada en SSR (no hay `navigator.serviceWorker`).
    provideServiceWorker('ngsw-worker.js', {
      enabled: environment.production,
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
