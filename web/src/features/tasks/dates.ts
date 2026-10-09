// The task deadline between the input field and the backend. `VDateInput` works with `Date`, the
// backend with a string, and the conversion in the two places (the task form and the task page)
// must be one and the same: if they diverged, a deadline set in one window would read a day
// earlier in the other.
//
// Conversion goes through the DISPLAY ZONE (`displayZone`), not straight through UTC. In the
// database a deadline is a moment in time, in the UI a calendar date, and what links them is the
// zone the person is looking from: "by September 30" means "by the end of September 30 on my
// clock". If we computed end of day in UTC, any zone east of Greenwich would show October 1 in
// the list — while the task page would show the 30th, since the field takes the date from the
// string as is.
import { DateTime } from 'luxon'

import { displayZone } from '@/shared/utils/date'

/** Backend string (SQL, UTC) → calendar day in the display zone. */
function zoned(value: string | null): DateTime | null {
  if (!value) return null
  const dt = DateTime.fromSQL(value, { zone: 'utc' }).setZone(displayZone())
  return dt.isValid ? dt : null
}

/**
 * Backend string → `Date` for the field. The noon in the constructor is not decoration: without
 * it, conversion to UTC at western offsets rolls the date back by a day.
 */
export function parseDay(value: string | null): Date | null {
  const dt = zoned(value)
  if (dt === null) return null
  return new Date(dt.year, dt.month - 1, dt.day, 12)
}

/** Calendar day of a stored value (`yyyy-MM-dd`) in the display zone — to compare with a draft. */
export function deadlineDay(value: string | null): string | null {
  return zoned(value)?.toFormat('yyyy-MM-dd') ?? null
}

/** Day picked in the field (`yyyy-MM-dd`): only the calendar part of the picker's `Date` matters. */
export function formatDay(value: Date | null): string | null {
  if (value === null) return null
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, '0'),
    String(value.getDate()).padStart(2, '0'),
  ].join('-')
}

/**
 * A deadline is a day in the UI and a moment in time in the database. "Done by such-and-such a
 * date" means the end of that day, so the picked date is sent with the last second of the day,
 * not midnight: otherwise a deadline set for today would be overdue from the very morning. The
 * last second is computed in the display zone and only then converted to UTC — the column lives
 * in UTC.
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
