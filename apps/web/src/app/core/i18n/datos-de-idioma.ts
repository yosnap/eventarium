import { registerLocaleData } from '@angular/common';
import localeEn from '@angular/common/locales/en';
import localeEs from '@angular/common/locales/es';

import { Idioma } from './idioma';

/**
 * Datos de formato (fechas, números, monedas) de cada idioma del catálogo. Son un
 * mecanismo distinto de Transloco: sin registrarlos, `DatePipe` y `DecimalPipe`
 * formatean en el inglés que Angular trae integrado aunque los textos estén en
 * otro idioma. El mapa es cerrado: un idioma nuevo sin datos no compila.
 */
const DATOS: Readonly<Record<Idioma, unknown[]>> = {
  'es-ES': localeEs,
  'en-US': localeEn,
};

export function registrarDatosDeIdioma(): void {
  for (const [idioma, datos] of Object.entries(DATOS)) {
    registerLocaleData(datos, idioma);
  }
}
