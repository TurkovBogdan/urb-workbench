import { useI18n } from 'vue-i18n'
import type { SetupField, SetupGroup } from './api'

// The ENV form labels live on the backend (`core_setup/keys.py`) as English fallback text. The
// translation key is derived from a stable identity already present in the response: the group
// code and the field's ENV key — the backend sends no separate key. A dictionary miss shows the
// backend's text, not the key path.
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
