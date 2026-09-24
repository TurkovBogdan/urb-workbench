import { i18n } from '@/plugins/i18n'

type Rule = (v: unknown) => true | string

/** Lowercase Latin letters, digits, hyphen and underscore. No spaces. */
export function isSlug(message?: string): Rule {
  return (v) => {
    const s = v == null ? '' : String(v)
    if (s === '') return true
    return /^[a-z0-9_-]+$/.test(s) || (message ?? i18n.global.t('common.validation.slug'))
  }
}
