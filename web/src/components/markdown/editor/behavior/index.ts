// Behaviour with no interface of its own: extensions and composables that draw nothing
// themselves but change what the document does in response to an action.
//
// The line with `controls/` is drawn by visibility: there is not a single button or menu here —
// only reactions to keys, paste and drag. Anything visible on screen lives either as a decoration
// (the drag source highlight, the flash after a move) or in `controls/`.
export { BlockMoves, type MoveTarget } from './blockMoves'
export { DragSource } from './dragSource'
export { MarkdownPaste } from './markdownPaste'
export { useDragPreview, type DragPreview } from './useDragPreview'
