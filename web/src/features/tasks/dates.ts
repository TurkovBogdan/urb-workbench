// Срок задачи между полем ввода и бэком. `VDateInput` работает с `Date`, бэк — со строкой, и
// перевод между ними в двух местах (форма задачи и её страница) обязан быть одним и тем же:
// разойдись они, срок, выставленный в одном окне, читался бы другим на сутки раньше.
//
// Перевод идёт через ПОЯС ПОКАЗА (`displayZone`), а не через UTC напрямую. Срок в базе — момент
// времени, в интерфейсе — календарное число, и связывает их пояс, в котором человек смотрит:
// «до 30 сентября» значит «до конца 30 сентября по моим часам». Считай мы конец суток в UTC, в
// любом поясе восточнее Гринвича список показывал бы первое октября — на странице задачи при этом
// стояло бы тридцатое, потому что поле берёт число из строки как есть.
import { DateTime } from 'luxon'

import { displayZone } from '@/shared/utils/date'

/** Строка бэка (SQL, UTC) → календарный день в поясе показа. */
function zoned(value: string | null): DateTime | null {
  if (!value) return null
  const dt = DateTime.fromSQL(value, { zone: 'utc' }).setZone(displayZone())
  return dt.isValid ? dt : null
}

/**
 * Строка бэка → `Date` для поля. Полдень в конструкторе не украшение: без него перевод в UTC на
 * западных смещениях откатывает дату на сутки назад.
 */
export function parseDay(value: string | null): Date | null {
  const dt = zoned(value)
  if (dt === null) return null
  return new Date(dt.year, dt.month - 1, dt.day, 12)
}

/** Календарный день значения из базы (`yyyy-MM-dd`) в поясе показа — для сравнения с черновиком. */
export function deadlineDay(value: string | null): string | null {
  return zoned(value)?.toFormat('yyyy-MM-dd') ?? null
}

/** День, выбранный в поле (`yyyy-MM-dd`): у `Date` из пикера значим только календарь, не время. */
export function formatDay(value: Date | null): string | null {
  if (value === null) return null
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, '0'),
    String(value.getDate()).padStart(2, '0'),
  ].join('-')
}

/**
 * Срок в интерфейсе — день, а в базе момент времени. «Успеть к такому-то числу» означает конец
 * этого дня, поэтому выбранная дата уезжает с последней секундой суток, а не с полуночью: иначе
 * срок, назначенный на сегодня, оказывался бы просроченным с самого утра. Последняя секунда
 * считается в поясе показа и уже оттуда переводится в UTC — в нём живёт колонка.
 */
export function formatDeadline(value: Date | null): string | null {
  if (value === null) return null
  return DateTime.fromObject(
    {
      year: value.getFullYear(),
      month: value.getMonth() + 1,
      day: value.getDate(),
      hour: 23,
      minute: 59,
      second: 59,
    },
    { zone: displayZone() },
  )
    .toUTC()
    .toFormat('yyyy-MM-dd HH:mm:ss')
}
