/**
 * «Сколько внутри» одной строкой — для окон, которые спрашивают про удаление.
 *
 * Пространство не знает, что в нём лежит: счётчики объявляют модули поверх, и их набор зависит
 * от состава приложения. Поэтому текст собирается из того, что приехало, а не пишется в словаре
 * перечислением зон и задач — иначе каждый новый модуль правил бы чужую фразу.
 *
 * Подпись берётся по ключу счётчика (`label_key`) из словаря модуля-владельца. В строку она
 * попадает со строчной буквы: в карточке это заголовок колонки («Зон»), а в предложении —
 * перечисление.
 */

import type { WorkspaceListRow } from './api'

type Translate = (key: string) => string

/** Есть ли внутри хоть что-то: нули не показываем — пустое пространство так и говорит. */
export function hasContent(workspace: WorkspaceListRow | null): boolean {
  return (workspace?.counters ?? []).some((counter) => counter.count > 0)
}

/** «зон: 2, задач: 12» — только ненулевое, в порядке, который задал бэк. */
export function contentSummary(
  workspace: WorkspaceListRow | null,
  t: Translate,
): string {
  return (workspace?.counters ?? [])
    .filter((counter) => counter.count > 0)
    .map((counter) => `${t(counter.label_key).toLocaleLowerCase()}: ${counter.count}`)
    .join(', ')
}
