// The full-screen viewer a picture in the document opens. One per editor (`MarkdownEditor.vue`
// hosts it and provides the opener); a picture node asks for it rather than mounting a dialog of
// its own per picture.
import type { InjectionKey } from 'vue'

/**
 * Show the picture `code` full screen; `gallery` — the codes of its gallery to page through, in
 * order; `at` — where the picture stands in the document now (its node's `getPos`): when the viewer
 * closes, the field takes the focus back and selects that picture.
 */
export type OpenPicture = (code: string, gallery: string[], at: () => number | undefined) => void

export const OPEN_PICTURE: InjectionKey<OpenPicture> = Symbol('open-picture')

/**
 * Enter on a selected picture opens it: the editor's keymap sees the key, but only the picture's
 * view knows its gallery, so the keymap sends this event to the view's element.
 */
export const OPEN_PICTURE_EVENT = 'md-image-open'
