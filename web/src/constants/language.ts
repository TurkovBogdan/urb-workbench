// Interface language. The choice is stored like the theme (registry key `interface_language` in
// core_interface) and drives vue-i18n, Vuetify's own strings and the `auto` date format together:
// language and region are one setting here.
//
// Labels are endonyms and are never translated — a person looking for their language must
// recognise it whatever the interface is currently set to. The flag only stands next to the
// label: a flag names a country, not a language.

export type AppLocale = 'en' | 'ru'

export interface LanguageOption {
  code: AppLocale
  label: string
  // ISO 3166-1 alpha-2 → assets/flags/<flag>.svg
  flag: string
}

export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { code: 'en', label: 'English', flag: 'gb' },
  { code: 'ru', label: 'Русский', flag: 'ru' },
]

export const DEFAULT_LANGUAGE: AppLocale = 'en'

// A cached value from an older build or a hand-edited storage entry must not reach vue-i18n as
// an unknown locale — every string would render as its key path.
export function appLocale(raw: string): AppLocale {
  return LANGUAGE_OPTIONS.some((option) => option.code === raw) ? (raw as AppLocale) : DEFAULT_LANGUAGE
}

// Circular flags vendored from HatScripts/circle-flags (MIT), as SVG files rather than emoji:
// Windows renders flag emoji as bare letters. Only the files in the folder reach the bundle.
const flagModules = import.meta.glob<string>('@/assets/flags/*.svg', {
  eager: true,
  query: '?url',
  import: 'default',
})

const FLAG_URLS: Record<string, string> = Object.fromEntries(
  Object.entries(flagModules).map(([path, url]) => [path.split('/').pop()!.replace('.svg', ''), url]),
)

// Empty when the file is missing — the caller hides the image rather than showing a broken one.
export function flagUrl(flag: string): string {
  return FLAG_URLS[flag] ?? ''
}
