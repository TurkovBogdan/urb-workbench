import { useI18n } from 'vue-i18n'
import type { TaskInfo } from './api'

type Identity = Pick<TaskInfo, 'module' | 'code'>
type Field = 'name' | 'short' | 'description'

// A job's name/description live on the backend (`NAME`/`DESCRIPTION` of the job class) and
// arrive in the payload. The translation KEY is derived from the stable `(module, code)` pair —
// the backend sends no separate key.
//
// Lookup order per field:
//   1. `<module>.task.<code>.<field>` — the module feature's own dictionary
//   2. `core_monitoring.catalog.<module>.<code>.<field>` — catch-all for modules without a frontend feature (e.g. `core`)
//   3. the literal from the backend (`info.name` / `info.description`) — so untranslated/new
//      jobs still render instead of leaking a raw key
export function useTaskLabels() {
  const { t, te } = useI18n()

  function pick(id: Identity, field: Field, fallback: string): string {
    const own = `${id.module}.task.${id.code}.${field}`
    if (te(own)) return t(own)
    const catalog = `core_monitoring.catalog.${id.module}.${id.code}.${field}`
    if (te(catalog)) return t(catalog)
    return fallback
  }

  return {
    taskName: (info: Identity & Pick<TaskInfo, 'name'>) => pick(info, 'name', info.name),
    taskNameShort: (info: Identity & Pick<TaskInfo, 'name'>) =>
      pick(info, 'short', pick(info, 'name', info.name)),
    taskDescription: (info: Identity & Pick<TaskInfo, 'description'>) =>
      pick(info, 'description', info.description),
  }
}
