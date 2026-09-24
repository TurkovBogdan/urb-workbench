import { createI18n } from 'vue-i18n'
import { en as vuetifyEn, ru as vuetifyRu } from 'vuetify/locale'

import { DEFAULT_LANGUAGE, type AppLocale } from '@/constants/language'
import commonEn from '@/locales/en.json'
import commonRu from '@/locales/ru.json'
// Root-level dictionary (not a module one). design-system is template chrome, not a
// domain module, but keeps its own namespace so t('design-system.*') stays stable.
import designSystemEn from '@/locales/design-system/en.json'
import designSystemRu from '@/locales/design-system/ru.json'
import { PLURAL_RULES } from './plural'

export type { AppLocale } from '@/constants/language'

type Messages = Record<string, unknown>

// Every language root is spelled out as its own literal: `import.meta.glob` accepts only literals,
// and a dictionary the pattern misses is lost silently — the interface starts rendering key paths
// instead of text. A pattern that matches nothing is harmless.
const moduleDictionaries = {
  en: import.meta.glob<{ default: Messages }>(
    ['@/features/*/locales/en.json', '@/modules/*/locales/en.json'],
    { eager: true },
  ),
  ru: import.meta.glob<{ default: Messages }>(
    ['@/features/*/locales/ru.json', '@/modules/*/locales/ru.json'],
    { eager: true },
  ),
}

function collectModuleMessages(locale: AppLocale): Messages {
  const out: Messages = {}
  const dictionaries = moduleDictionaries[locale]
  for (const path in dictionaries) {
    const match = path.match(/\/(?:features|modules)\/([^/]+)\/locales\/\w+\.json$/)
    if (!match) continue
    out[match[1]] = dictionaries[path].default
  }
  return out
}

// `$vuetify` holds Vuetify's own component strings (VDataTable, VPagination, …);
// the locale adapter in plugins/vuetify.ts reads them from this same tree.
const messages = {
  en: {
    $vuetify: vuetifyEn,
    common: commonEn,
    'design-system': designSystemEn,
    ...collectModuleMessages('en'),
  },
  ru: {
    $vuetify: vuetifyRu,
    common: commonRu,
    'design-system': designSystemRu,
    ...collectModuleMessages('ru'),
  },
}

// The language itself is not decided here: the settings store owns it (`interface_language`,
// synced with the backend) and applies it through `setLocale` before the first paint.
// Russian is the fallback because it is the authoring language — the one dictionary that is
// always complete — so a key not yet translated shows Russian text rather than its key path.
export const i18n = createI18n({
  legacy: false,
  globalInjection: true, // expose `$t`/`$te` in templates (needed where a v-for var shadows `t`)
  locale: DEFAULT_LANGUAGE,
  fallbackLocale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  pluralRules: PLURAL_RULES,
  messages,
})

// The single way to switch language: vue-i18n (Vuetify follows through its adapter) and
// `<html lang>`, which screen readers and hyphenation read.
export function setLocale(locale: AppLocale): void {
  i18n.global.locale.value = locale
  if (typeof document !== 'undefined') document.documentElement.lang = locale
}

setLocale(DEFAULT_LANGUAGE)

export default i18n
