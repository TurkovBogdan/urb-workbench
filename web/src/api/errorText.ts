import { ApiError } from './client/createClient'
import { i18n } from '@/plugins/i18n'

// Human-readable failure text. The backend names the reason it understands with a code (plus
// `params` for interpolation), and the text in the interface language comes from our dictionary:
//   `<module>.<entity>.<reason>` → `<module>.error.<entity>.<reason>` — the feature's dictionary;
//   a code without a module (and the client's own codes: `network`/`timeout`/`protocol`) →
//   `common.errors.<code>`.
// A code the dictionary doesn't know, and a failure without a code, show the English fallback text
// `error` from the response; failing that, a generic text. Works outside components (stores, the
// API client) — reads the global i18n instance.
export function errorText(e: unknown): string {
  const { t, te } = i18n.global

  if (e instanceof ApiError) {
    // Hit the rate limit. The response carries `Retry-After`, and naming the seconds is more honest
    // than "try again later": otherwise the person clicks again and again, extending their own
    // window.
    if (e.status === 429) {
      return e.retryAfter === undefined
        ? t('common.errors.throttled')
        : t('common.errors.throttled_wait', { seconds: e.retryAfter })
    }

    const key = e.code ? dictionaryKey(e.code) : null
    if (key && te(key)) return t(key, e.params ?? {})

    return e.message || t('common.errors.generic')
  }

  return e instanceof Error && e.message ? e.message : t('common.errors.generic')
}

// `common.` — the shared dictionary is mounted under this namespace (`plugins/i18n.ts`); a bare
// `errors.*` would miss silently.
function dictionaryKey(code: string): string {
  const [module, ...rest] = code.split('.')
  return rest.length ? `${module}.error.${rest.join('.')}` : `common.errors.${code}`
}
