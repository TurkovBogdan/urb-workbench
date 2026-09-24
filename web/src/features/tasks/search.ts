// Глубина поиска по списку задач: какие области переключает поле и как они ложатся на стор.
//
// Стог набирается слоями, а не одной глубиной. Заголовок и цель — основа, они в стоге всегда:
// ими задача названа в списке, и выключаемая основа означала бы поиск, не находящий искомое по
// имени. Остальное лежит в телах, которых в строке списка нет вовсе, и каждый слой включается
// отдельно — постановка, план с этапами, журнал.
//
// Ключи совпадают с полями стора один в один, поэтому переходник между набором `SearchField`
// (массив включённых ключей) и тремя флагами сводится к перечислению — и живёт здесь, рядом с
// самими областями, а не в разметке панели.
import { computed, type WritableComputedRef } from 'vue'
import { IconClipboardText, IconListCheck, IconNotes } from '@tabler/icons-vue'

import type { SearchScope } from '@/components/SearchField.vue'

export const SCOPE_BRIEF = 'brief'
export const SCOPE_PLAN = 'plan'
export const SCOPE_JOURNAL = 'journal'

/** Включённые области поиска; все выключены — ищем только по заголовку и цели. */
export interface TaskSearchScopes {
  inBrief: boolean
  inPlan: boolean
  inJournal: boolean
}

export const NO_SCOPES: TaskSearchScopes = { inBrief: false, inPlan: false, inJournal: false }

export function anyScope(scopes: TaskSearchScopes): boolean {
  return scopes.inBrief || scopes.inPlan || scopes.inJournal
}

// По одной букве бэк читает все тела пространства ради мусорного ответа, поэтому клиент его и
// не зовёт — тот же порог, что у глубокого поиска в реестре исследований.
export const MIN_DEEP_QUERY_LENGTH = 2

const SCOPE_ICONS = {
  [SCOPE_BRIEF]: IconClipboardText,
  [SCOPE_PLAN]: IconListCheck,
  [SCOPE_JOURNAL]: IconNotes,
}

/** Набор областей для поля; подписи даёт место применения — словарь живёт у фичи. */
export function taskSearchScopes(label: (scope: string) => string): SearchScope[] {
  return Object.entries(SCOPE_ICONS).map(([key, icon]) => ({ key, icon, label: label(key) }))
}

export function taskScopesModel(
  scopes: () => TaskSearchScopes,
  apply: (next: TaskSearchScopes) => void,
): WritableComputedRef<string[]> {
  return computed({
    get: () => {
      const { inBrief, inPlan, inJournal } = scopes()
      return [
        ...(inBrief ? [SCOPE_BRIEF] : []),
        ...(inPlan ? [SCOPE_PLAN] : []),
        ...(inJournal ? [SCOPE_JOURNAL] : []),
      ]
    },
    set: (keys) =>
      apply({
        inBrief: keys.includes(SCOPE_BRIEF),
        inPlan: keys.includes(SCOPE_PLAN),
        inJournal: keys.includes(SCOPE_JOURNAL),
      }),
  })
}
