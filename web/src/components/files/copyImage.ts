// The picture itself to the clipboard — the picture menu's «Скопировать содержимое»: pasted into a
// chat, a document or an image editor, it arrives as a picture, not as its address.
//
// A browser's clipboard takes a picture as PNG only, so any other kind — JPEG, WebP, a GIF (its
// first frame), an SVG — is drawn on a canvas and taken from there. The PNG goes to the clipboard as
// a promise: the write has to start inside the click that asked for it, while the bytes are still
// on their way, or the browser refuses it as not asked by the person.

/** An SVG without a size of its own is drawn this wide, its height by its proportions. */
const SIZELESS_WIDTH = 1024

export async function copyImage(src: string): Promise<void> {
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': asPng(src) })])
}

async function asPng(src: string): Promise<Blob> {
  const response = await fetch(src)
  if (!response.ok) throw new Error(`The picture did not load (${response.status})`)
  const blob = await response.blob()
  if (blob.type === 'image/png') return blob
  return redraw(blob)
}

async function redraw(blob: Blob): Promise<Blob> {
  const url = URL.createObjectURL(blob)
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    const width = image.naturalWidth || SIZELESS_WIDTH
    const height = image.naturalHeight || Math.round(width * 0.75)
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) throw new Error('No canvas to draw the picture on')
    context.drawImage(image, 0, 0, width, height)
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((png) => (png ? resolve(png) : reject(new Error('The picture did not turn into PNG'))), 'image/png')
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}
