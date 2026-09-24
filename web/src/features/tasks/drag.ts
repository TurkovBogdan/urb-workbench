// Куда легла перетащенная строка — одно правило на все контейнеры списка задач.
//
// ПОЧЕМУ НЕ `previousElementSibling`. К моменту `onEnd` разметка уже не та, что была в момент
// броска: `vue-draggable-plus` держит порядок в переданном ему массиве и ОТКАТЫВАЕТ перестановку
// в DOM, чтобы дальше её сделал Vue из своего списка. Сосед, прочитанный из разметки после
// отката, — это сосед по старому порядку, то есть неверная позиция. Симптом ровно такой: тащишь
// строку вверх, а уезжает вниз.
//
// Поэтому позиция считается по `newIndex` библиотеки и по кодам контейнера, из которых исключена
// сама переехавшая строка. Правило одинаково работает и когда откат случился, и когда нет, и для
// переноса в другой контейнер — там переехавшей строки в целевом ряду просто ещё нет.

/** Коды строк контейнера в их порядке; переехавшая исключена. */
function neighbours(container: HTMLElement, movedCode: string): string[] {
  return [...container.children]
    .map((child) => (child as HTMLElement).dataset?.code)
    .filter((code): code is string => !!code && code !== movedCode)
}

/**
 * Код строки, ПОД которую легла переехавшая; `null` — она встала первой.
 *
 * `newIndex` — место среди всех строк контейнера, поэтому выше неё стоит `newIndex - 1`-я из
 * остальных.
 */
export function anchorAfterDrop(
  container: HTMLElement,
  movedCode: string,
  newIndex: number | undefined,
): string | null {
  // Шапка карточки группы (`GroupDropZone`): места внутри неё нет, задача встаёт в КОНЕЦ ряда
  // группы — после той, что шапка назвала последней. Так же кладёт задачу и `tasks_regroup`.
  if (container.dataset.drop === 'end') {
    const last = container.dataset.after || null
    return last === movedCode ? null : last
  }
  if (!newIndex) return null
  return neighbours(container, movedCode)[newIndex - 1] ?? null
}
