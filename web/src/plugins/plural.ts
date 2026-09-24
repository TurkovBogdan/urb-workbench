// Plural rules for vue-i18n: which of the `|`-separated forms of a message a number takes.
//
// Kept free of imports on purpose — `tests/apps/test_web_plural.py` runs this file under Node to
// check the rules against the real dictionary strings.
//
// A message with a number is written with as many forms as its language needs:
//   en — `one | other`, or `zero | one | other` when zero reads differently;
//   ru — `one | few | many` (1, 21 коммит · 2–4, 22 коммита · 0, 5–20, 11–14 коммитов),
//        or `zero | one | few | many` when zero reads differently.

export type PluralRule = (choice: number, choicesLength: number) => number

export const englishPlural: PluralRule = (choice, choicesLength) => {
  const n = Math.abs(choice)
  if (choicesLength === 3) return Math.min(n, 2)
  return n === 1 ? 0 : 1
}

export const russianPlural: PluralRule = (choice, choicesLength) => {
  const n = Math.abs(choice)
  const zeroForm = choicesLength === 4
  if (zeroForm && n === 0) return 0
  const first = zeroForm ? 1 : 0
  const lastDigit = n % 10
  const lastTwo = n % 100
  if (lastDigit === 1 && lastTwo !== 11) return first
  if (lastDigit >= 2 && lastDigit <= 4 && (lastTwo < 12 || lastTwo > 14)) return first + 1
  return first + 2
}

export const PLURAL_RULES = { en: englishPlural, ru: russianPlural }
