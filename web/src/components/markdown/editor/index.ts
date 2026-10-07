// Public entry point of the editing zone.
//
// What sticks out is the component — and the bridge. The bridge is not leaked internals but part
// of the contract: its round trip is the only way to check that the editor is fit for a real body,
// and the design-system page exercises exactly that. Everything else — schema, chrome,
// behaviour — is assembly detail, with no reason to be imported from outside.
export { default as MarkdownEditor } from './MarkdownEditor.vue'
export { docToMarkdown, markdownToDoc, UNSUPPORTED } from './bridge'
