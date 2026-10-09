// Printing a document to a virtual printer — the same as "Save as PDF" in the browser's print
// dialog.
//
// What gets printed is not the screen the button was pressed on but a separate print address of
// the same app: around the document on the page sit the navigation rail, the header and section
// cards, and hiding them with `@media print` rules would have to be redone for every new block. A
// hidden frame opens the print page, where the document is rendered alone on a blank sheet, and
// prints it: `print()` called on the frame's window sends the FRAME's document to the printer,
// not the host page's.

const PRINT_SIGNAL = 'app-print'

interface PrintSignalMessage {
  signal: typeof PRINT_SIGNAL
  /** Empty — the document is ready to print; otherwise the failure text that left nothing to print. */
  error: string
}

// An A4 sheet at 96 dpi. The frame size is not decoration on an invisible element: diagram and
// table layout is computed from the container width, and in a zero-width frame it would be laid
// out for a sheet that doesn't exist.
const FRAME_WIDTH_PX = 794
const FRAME_HEIGHT_PX = 1123

// How long to wait for the ready signal: the print page has to re-fetch the research, parse the
// body, render diagrams and wait for fonts.
const READY_TIMEOUT_MS = 60_000

// Some browsers return from `print()` without waiting for printing to finish. A frame removed
// immediately would take the document being printed with it, so it lives a little longer after
// sending.
const FRAME_KEEP_MS = 2000

function postSignal(error: string): void {
  const message: PrintSignalMessage = { signal: PRINT_SIGNAL, error }
  window.parent.postMessage(message, window.location.origin)
}

/** Called by the print page when its document is fully rendered and can be sent to the printer. */
export function announcePrintReady(): void {
  postSignal('')
}

/** Called by the print page when there will be no document: nothing to print, nothing to wait for. */
export function announcePrintFailure(error: string): void {
  postSignal(error)
}

/**
 * Print an app page by its address.
 *
 * Resolves once the document has gone to the printer; rejects with the print page's failure text —
 * or with an empty one when it didn't answer at all (then only the page itself knows why).
 */
export function printPage(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe')
    frame.setAttribute('aria-hidden', 'true')
    frame.src = url
    frame.style.cssText =
      `position:fixed;left:-10000px;top:0;border:0;width:${FRAME_WIDTH_PX}px;height:${FRAME_HEIGHT_PX}px;`

    const readyTimer = setTimeout(() => finish(new Error('')), READY_TIMEOUT_MS)

    function finish(failure: Error | null): void {
      clearTimeout(readyTimer)
      window.removeEventListener('message', onSignal)
      if (failure) {
        frame.remove()
        reject(failure)
        return
      }
      setTimeout(() => frame.remove(), FRAME_KEEP_MS)
      resolve()
    }

    function onSignal(event: MessageEvent): void {
      const message = event.data as PrintSignalMessage | undefined
      if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return
      if (message?.signal !== PRINT_SIGNAL) return

      if (message.error) {
        finish(new Error(message.error))
        return
      }

      // Focusing the frame is mandatory: the browser prints the active window's document, and
      // without it the host page with the whole interface would go to the printer.
      frame.contentWindow?.focus()
      frame.contentWindow?.print()
      finish(null)
    }

    window.addEventListener('message', onSignal)
    document.body.appendChild(frame)
  })
}
