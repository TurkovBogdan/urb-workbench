// Saving a stored file to disk under its name — «Скачать» of the media panel, the picture menu and
// a file's hover card, one rule for all.
//
// The storage's download address takes the name the file is saved under (`core_storage_view`), and
// adds the file's own extension to a name that has none — a title the holder gave usually has none,
// and only the storage knows the extension. An empty title leaves the name out: the storage then
// saves the file under its code.

/** The name to save under: the title the holder gave; empty — the storage's neutral one. */
export function downloadName(title: string): string {
  return title.trim()
}

/** The storage's download address of a stored file shown at `link`. */
export function downloadHref(link: string, name: string): string {
  return name ? `${link}/download/${encodeURIComponent(name)}` : `${link}/download`
}

/** Start the download from code, as a click on a download link would. */
export function startDownload(href: string, name: string): void {
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = name
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}
