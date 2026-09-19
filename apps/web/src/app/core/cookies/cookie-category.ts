/** Categorías del banner de cookies. `necessary` nunca se puede rechazar. */
export type CookieCategory = 'necessary' | 'analytics' | 'marketing';

export const NON_ESSENTIAL_CATEGORIES: readonly CookieCategory[] = ['analytics', 'marketing'];
