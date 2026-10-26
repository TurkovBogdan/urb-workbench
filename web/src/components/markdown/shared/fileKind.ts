// Which kind of file a file's pill names — the class that gives it the glyph of that kind
// (`md-ref--kind-pdf` in `document.css`). The kinds are the files panel's (`fileKind`), so a pill
// and the row of the same file in the panel show the same sign. The stored file's type decides,
// the name only when the type says nothing: a holder may title a PDF without its extension.
//
// One answer for the viewer and the editor. A code that is not a file, a file with no preview yet
// and a file that is gone wear no kind; a kind with no glyph of its own (`other`) neither — the
// pill keeps the plain file glyph.
import type { PreviewRecord } from '@/api/lookup'
import { fileKind } from '@/shared/utils/file-icon'
import { refIsFile } from './contracts'

const KIND_CLASS_PREFIX = 'md-ref--kind-'

/** The pill's kind class, or `''` when it has none. */
export function fileKindClass(code: string, record: PreviewRecord | undefined): string {
  if (!refIsFile(code) || !record || record.error) return ''
  const kind = fileKind(record.title, record.mime)
  return kind === 'other' ? '' : `${KIND_CLASS_PREFIX}${kind}`
}

/** Put the kind class on a pill drawn outside Vue, taking off the one an earlier preview gave it. */
export function setFileKindClass(pill: HTMLElement, kindClass: string): void {
  for (const name of [...pill.classList]) {
    if (name.startsWith(KIND_CLASS_PREFIX) && name !== kindClass) pill.classList.remove(name)
  }
  if (kindClass) pill.classList.add(kindClass)
}
