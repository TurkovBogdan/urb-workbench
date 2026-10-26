// Files dragged in from the computer: whether a drag carries any, which of what was dropped are
// folders, and how big is too big.
//
// A folder comes into a drop as a "file" of its own — a name, no type, a size the file system made
// up — and sent as one it would arrive as garbage or fail with nothing to say why. The browser tells
// a folder by the drop item's entry (`webkitGetAsEntry()`), and only while the drop event lasts: the
// item list is emptied the moment the handler returns. So a drop is sorted in two steps — at once,
// by the entries, and later, for a file the browser gave no entry for, by reading its first byte: a
// folder handed over as a file cannot be read. A file that has a type is a file; only a type-less
// one is read. An empty file that reads is a file too.
//
// Framework-free: checked under Node (`tests/apps/web_file_drop.mjs`).

/** Whether a drag carries files from outside the page. During the drag only the types are known. */
export function carriesFiles(types: ArrayLike<string> | null | undefined): boolean {
  return Array.from(types ?? []).includes('Files')
}

/**
 * The names of the files a drop only points at: some apps hand a dragged file over as its address on
 * the disk (`file:///home/…/report.html` in `text/uri-list`) and not as the file — a browser's own
 * list of downloads, a messenger. A page cannot read a `file://` address, so there is nothing to
 * send, and left to itself the field would type the address in as text. Some put it in UTF-16, every
 * character trailed by a zero, which reads as `f i l e : / / /`; the zeros are dropped.
 *
 * Empty unless every address the drop names is a local file: a link from a page is a link.
 */
export function droppedPaths(data: { getData(format: string): string } | null | undefined): string[] {
  if (!data) return []
  const raw = data.getData('text/uri-list') || data.getData('text/plain')
  const lines = raw
    .replace(/\u0000/g, '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
  if (!lines.length || !lines.every((line) => /^file:\/\//i.test(line))) return []
  return lines.map((line) => {
    const last = line.replace(/\/+$/, '').split('/').pop() ?? line
    try {
      return decodeURIComponent(last)
    } catch {
      return last
    }
  })
}

/** The size ceiling, `null` — not known, nothing is refused here. Over means larger, as the server counts. */
export function overLimit(size: number, limit: number | null | undefined): boolean {
  return typeof limit === 'number' && size > limit
}

interface EntryLike {
  isDirectory: boolean
  name: string
}

interface DropItemLike {
  kind: string
  getAsFile(): File | null
  webkitGetAsEntry?: () => EntryLike | null
}

/** A drop's data, as much of a `DataTransfer` as the sorting needs. */
export interface DropDataLike {
  files: ArrayLike<File>
  items?: ArrayLike<DropItemLike>
}

/**
 * What a drop brings, sorted as far as the event lets: `files` — everything that is not known to be
 * a folder, in the order dropped; `unsure` — those of them that still have to be read to tell.
 */
export interface SortedDrop {
  files: File[]
  folders: string[]
  unsure: File[]
}

/** Sort a list of files nobody said anything about — a paste, a picker. */
export function sortFiles(files: Iterable<File>): SortedDrop {
  const all = Array.from(files)
  return { files: all, folders: [], unsure: all.filter((file) => !file.type) }
}

/** The first step, inside the drop event: the entries say file or folder while they still can. */
export function sortDropped(data: DropDataLike | null | undefined): SortedDrop {
  if (!data) return { files: [], folders: [], unsure: [] }
  const items = Array.from(data.items ?? []).filter((item) => item.kind === 'file')
  if (!items.length) return sortFiles(Array.from(data.files))
  const sorted: SortedDrop = { files: [], folders: [], unsure: [] }
  for (const item of items) {
    const entry = item.webkitGetAsEntry?.() ?? null
    const file = item.getAsFile()
    if (entry?.isDirectory) {
      sorted.folders.push(entry.name || file?.name || '')
      continue
    }
    if (!file) continue
    sorted.files.push(file)
    if (!entry && !file.type) sorted.unsure.push(file)
  }
  return sorted
}

/** The fallback test: a folder handed over as a file refuses to be read. */
export async function isReadable(file: Blob): Promise<boolean> {
  try {
    await file.slice(0, 1).arrayBuffer()
    return true
  } catch {
    return false
  }
}

/** The second step, after the event: the `unsure` files are read, and those that do not read are folders. */
export async function settleDropped(
  sorted: SortedDrop,
  readable: (file: Blob) => Promise<boolean> = isReadable,
): Promise<{ files: File[]; folders: string[] }> {
  if (!sorted.unsure.length) return { files: sorted.files, folders: sorted.folders }
  const folders = [...sorted.folders]
  const unreadable = new Set<File>()
  for (const file of sorted.unsure) {
    if (await readable(file)) continue
    unreadable.add(file)
    folders.push(file.name)
  }
  return { files: sorted.files.filter((file) => !unreadable.has(file)), folders }
}
