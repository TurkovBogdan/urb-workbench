// The order of a holder's files when only some of them are on screen.
//
// A holder puts the codes it is sent on top and the rest below, so a reorder of the shown cards
// alone would push every unseen file to the end. The order goes out whole instead: the shown codes,
// in their new order, take the places the shown files held in the holder's list, and an unseen one
// keeps its own between them.

/**
 * `all` — the holder's codes in its order; `shown` — the codes on screen, in their new order, each
 * one of `all`. The answer is `all` with the shown places filled by `shown`.
 */
export function placeShown(all: readonly string[], shown: readonly string[]): string[] {
  const onScreen = new Set(shown)
  let next = 0
  return all.map((code) => (onScreen.has(code) ? shown[next++] : code))
}
