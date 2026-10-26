// How a page edits what its entity calls a stored file, or takes the file out of it. The page whose
// entity holds files — a task, a codex note — provides it; the media panel under a picture shown
// full screen saves through it, the picture menu's «Удалить файл» cuts the link through it. Both live in the
// foundation and know no module, so the page lends them the calls they need. Where nothing is
// provided, they only read.
import type { InjectionKey } from 'vue'

export interface FileBindingEditor {
  /** Save what the page's entity calls the file (`FILE@…`) and says is in it; a field left out stays. */
  save: (file: string, patch: { title?: string; description?: string }) => Promise<void>
  /**
   * Cut the page's entity's link to the file. Nothing is deleted here: the storage marks the file
   * deleted once no live owner is left, and its cleanup removes it later.
   */
  remove: (file: string) => Promise<void>
  /** The entity is in the trash: its files are read, not edited. */
  readonly: () => boolean
}

export const FILE_BINDING_EDITOR: InjectionKey<FileBindingEditor> = Symbol('file-binding-editor')
