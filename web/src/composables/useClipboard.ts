import { onUnmounted, ref, type Ref } from 'vue'

/**
 * Copy to clipboard with a self-clearing "copied" mark — what any copy button needs.
 *
 * The mark holds THE COPIED TEXT ITSELF, not a flag: in a list of buttons a boolean flag would
 * light up on every row at once. A button with a single target just uses `isCopied(its value)`.
 *
 * The textarea fallback is not overcaution: under Qt WebEngine the async clipboard API rejects the
 * write while the document is not focused.
 */
export function useClipboard(resetAfter = 1800): {
  copiedText: Ref<string | null>
  copy: (text: string) => Promise<void>
  isCopied: (text: string) => boolean
} {
  const copiedText = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined

  function writeViaHiddenTextarea(text: string): void {
    const el = document.createElement('textarea')
    el.value = text
    el.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0'
    document.body.appendChild(el)
    el.focus()
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
  }

  async function copy(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      writeViaHiddenTextarea(text)
    }

    copiedText.value = text
    clearTimeout(timer)
    timer = setTimeout(() => { copiedText.value = null }, resetAfter)
  }

  const isCopied = (text: string): boolean => copiedText.value === text

  // Otherwise the timer fires on an unmounted component and Vue complains about the ref write.
  onUnmounted(() => clearTimeout(timer))

  return { copiedText, copy, isCopied }
}
