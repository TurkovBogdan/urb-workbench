// Escaping is where a serializer silently rewrites the user's text.
//
// A file of its own because this is not a printing detail but knowledge in its own right: every
// rule below is narrow on purpose and fires only where the character would otherwise open markup.
// Unconditional escaping is exactly where off-the-shelf markdown serializers break — they put a
// backslash before every special character, and the text comes back different from what was
// written.

export function escapeText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/([`*])/g, '\\$1')
    // CommonMark ignores an underscore inside a word, so escaping it there is pure noise:
    // `snake_case` must not come back as `snake\_case`. Only an underscore at a word boundary
    // opens emphasis.
    .replace(/(?<!\w)_|_(?!\w)/g, '\\_')
    // `~~` is strikethrough; a single tilde stays a tilde.
    .replace(/~~/g, '\\~\\~')
    // A bracket starts a link only if the run closes with `](`. Escaping every bracket would turn
    // a written `[x]` into `\[x\]`.
    .replace(/\[(?=[^\]\n]*\]\()/g, '\\[')
}

// A character becomes a block marker only at the start of its line, so the rule runs on the
// assembled line rather than on a text node: `#` mid-sentence is just a hash.
export function escapeLineStarts(value: string): string {
  return value
    .split('\n')
    .map((line) => line
      .replace(/^(\s*)([#>+-])/, '$1\\$2')
      .replace(/^(\s*)(\d+)([.)])/, '$1$2\\$3'))
    .join('\n')
}
