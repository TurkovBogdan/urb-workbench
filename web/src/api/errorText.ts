import { ApiError } from './client/createClient'
import { i18n } from '@/plugins/i18n'

// Человеческий текст отказа. Бэкенд называет понятную ему причину кодом (плюс `params` для
// подстановки), а текст на языке интерфейса даёт свой словарь:
//   `<модуль>.<сущность>.<причина>` → `<модуль>.error.<сущность>.<причина>` — словарь фичи;
//   код без модуля (и коды самого клиента: `network`/`timeout`/`protocol`) → `common.errors.<code>`.
// Код, которого словарь не знает, и отказ без кода показывают английский запасной текст `error`
// из ответа; нет и его — общий текст. Работает вне компонентов (сторы, клиент API) — читает
// глобальный инстанс i18n.
export function errorText(e: unknown): string {
  const { t, te } = i18n.global

  if (e instanceof ApiError) {
    // Упёрлись в лимит. Ответ несёт `Retry-After`, и назвать секунды честнее, чем «попробуйте
    // позже»: человек иначе жмёт снова и снова, продлевая себе же окно.
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

// `common.` — под этим пространством смонтирован общий словарь (`plugins/i18n.ts`); голый
// `errors.*` промахнулся бы молча.
function dictionaryKey(code: string): string {
  const [module, ...rest] = code.split('.')
  return rest.length ? `${module}.error.${rest.join('.')}` : `common.errors.${code}`
}
