// "Export to PDF" of a document page: prints the document's print address (`PrintDocument`) in a
// hidden frame, and the browser's print dialog — "Save as PDF" — takes it from there. The page the
// action sits on is not what goes to the printer: around the document there it has the app's frame.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, type RouteLocationRaw } from 'vue-router'

import { pushToast } from '@/composables/useToasts'
import { printPage } from '@/shared/utils/print'

export function usePrint() {
  const { t } = useI18n()
  const router = useRouter()

  // The sheet takes seconds to get ready (the document is fetched anew, diagrams drawn, pictures
  // loaded). The action lives in a menu that closes on the click, so the page shows this on the
  // menu's own button; a second request meanwhile would open a second frame and a second dialog.
  const printing = ref(false)

  /**
   * Print the document at `to`. `prepare` sends what the page still holds unsaved and is awaited
   * first: the print page reads the document from the database, and text typed a moment ago would
   * be missing from the sheet.
   */
  async function print(to: RouteLocationRaw, prepare?: () => Promise<unknown>): Promise<void> {
    if (printing.value) return
    printing.value = true
    try {
      await prepare?.()
      await printPage(router.resolve(to).href)
    } catch (e) {
      pushToast(e instanceof Error && e.message ? e.message : t('common.print.failed'))
    } finally {
      printing.value = false
    }
  }

  return { printing, print }
}
