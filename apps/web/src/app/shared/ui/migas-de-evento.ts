import { rutaEvento, rutaOrganizacion } from '../../core/routing/rutas-publicas';
import type { BreadcrumbItem } from './breadcrumb';

/** Organización tal y como llega en los contratos públicos (`PublicOrganizationRef`). */
export interface OrganizacionPublica {
  readonly slug: string;
  readonly name: string;
  readonly page_public: boolean;
}

interface EntradaMigas {
  /** Texto traducido de «Inicio». */
  readonly inicio: string;
  readonly organizacion: OrganizacionPublica;
  readonly eventoSlug: string;
  readonly eventoTitulo: string;
  /** Lo que sigue al evento (programa, sesión…); vacío en la ficha del evento. */
  readonly cola?: readonly BreadcrumbItem[];
}

/**
 * `Inicio › {Organización} › {Evento} › …`. La organización solo es un enlace
 * si tiene página pública; si no, es texto sin `href` (y sin foco).
 */
export function migasDeEvento(entrada: EntradaMigas): BreadcrumbItem[] {
  const { inicio, organizacion, eventoSlug, eventoTitulo, cola = [] } = entrada;
  const base: BreadcrumbItem[] = [
    { label: inicio, routerLink: ['/'] },
    {
      label: organizacion.name,
      routerLink: organizacion.page_public ? rutaOrganizacion(organizacion.slug) : undefined,
    },
  ];
  if (cola.length === 0) {
    return [...base, { label: eventoTitulo }];
  }
  return [
    ...base,
    { label: eventoTitulo, routerLink: rutaEvento(organizacion.slug, eventoSlug) },
    ...cola,
  ];
}
