// The markdown ↔ document bridge: two halves that cannot be trusted separately.
//
// The parsing half reads a body with the same markdown-it tokens as the renderer; the printing
// half assembles the text back. The model between them does not keep SPELLING — which marker,
// which fence, which escaping — so the goal is not "byte for byte", which no structural editor
// achieves, but a contract of three checkable points:
//
//   1. the second pass equals the first (stability);
//   2. the text does not change — no escaping is added that the parser did not require;
//   3. whatever cannot be carried is declared (`UNSUPPORTED`), not kept quiet.
//
// All three are checked by the round-trip panel on the design-system page.
export { markdownToDoc } from './markdownToDoc'
export { docToMarkdown } from './docToMarkdown'
export { restrict } from './restrict'
export { UNSUPPORTED } from './unsupported'
