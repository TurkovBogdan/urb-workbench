// Interface language. The choice is stored like the theme (registry key `interface_language` in
// core_interface) and drives vue-i18n, Vuetify's own strings and the `auto` date format together:
// language and region are one setting here.
//
// Labels are endonyms and are never translated — a person looking for their language must
// recognise it whatever the interface is currently set to.

export type AppLocale = 'en' | 'ru'

export interface LanguageOption {
  code: AppLocale
  label: string
}

export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { code: 'en', label: 'English' },
  { code: 'ru', label: 'Русский' },
]

export const DEFAULT_LANGUAGE: AppLocale = 'en'

// A cached value from an older build or a hand-edited storage entry must not reach vue-i18n as
// an unknown locale — every string would render as its key path.
export function appLocale(raw: string): AppLocale {
  return LANGUAGE_OPTIONS.some((option) => option.code === raw) ? (raw as AppLocale) : DEFAULT_LANGUAGE
}
