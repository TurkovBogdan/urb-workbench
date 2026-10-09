// What the bridge does not carry — a declaration, not a comment.
//
// The list is a file of its own for two reasons. It is thrown away ON INPUT, so a divergence shows
// up in the round trip on the showcase, not one day in a saved body. And it is the only honest
// answer to "can the editor be pointed at a real body": while the renderer shows a construct that
// does not exist here, editing through the editor will destroy it.

export const UNSUPPORTED = [
  'images',
  'footnotes',
  'raw HTML',
  'blocks inside list items',
  // Not a loss of meaning but a loss of spelling: `` `TYPE@hash` `` becomes a pill and prints
  // back as a bare code. It reads back into the same pill, so the second pass matches the first —
  // but the text did change, and the list has no right to keep quiet about it.
  'backticks around a whole code',
] as const
