import { useI18n } from 'vue-i18n'
import type { SetupField, SetupGroup } from './api'

// Подписи формы ENV живут на бэке (`core_setup/keys.py`) английским запасным текстом. Ключ
// перевода выводится из стабильной идентичности, которая уже есть в ответе: код группы и
// ENV-ключ поля — отдельного ключа бэк не шлёт. Промах словаря — текст бэка, а не путь ключа.
export function useSetupLabels() {
  const { t, te } = useI18n()

  function pick(key: string, fallback: string): string {
    return te(key) ? t(key) : fallback
  }

  return {
    groupTitle: (group: SetupGroup) => pick(`setup.group.${group.code}`, group.group),
    fieldLabel: (field: SetupField) => pick(`setup.field.${field.key}.label`, field.label),
    fieldDescription: (field: SetupField) =>
      pick(`setup.field.${field.key}.description`, field.description),
  }
}
