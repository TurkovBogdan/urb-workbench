// One import of an archive, from the file to the report — the same steps for a task and a codex.
//
// Upload (with its progress) → analysis → the plan with the person's choices → apply. The uploaded
// file waits on the server between the requests, so leaving the import half way gives it back
// (`discard`) rather than leaving it to the day's sweep.
//
// The apply may find the base changed since the plan was shown (`transfer_plan_changed`): the plan
// is read again, the choices that still fit are kept, and `planChanged` says so — the person checks
// the conflicts again rather than having choices made for another set applied.
import { computed, ref, shallowRef } from 'vue'

import { ApiError } from '@/api/client/internal'
import { errorText } from '@/api/errorText'
import {
  allChosen,
  carriedChoices,
  choose,
  chooseAll,
  presetChoices,
  type TransferChoice,
  type TransferPlanBase,
  type TransferUpload,
} from '@/components/transfer/types'

export interface TransferImportApi<P extends TransferPlanBase, R> {
  upload(file: File, onProgress: (loaded: number, total: number) => void, signal: AbortSignal): Promise<TransferUpload>
  analyze(uploadId: string): Promise<P>
  apply(uploadId: string, choices: Record<string, TransferChoice>, planToken: string): Promise<R>
  cancel(uploadId: string): Promise<void>
}

export type TransferPhase = 'pick' | 'upload' | 'analyze' | 'plan' | 'apply' | 'done'

const PLAN_CHANGED = 'transfer_plan_changed'

export function useTransferImport<P extends TransferPlanBase, R>(api: TransferImportApi<P, R>) {
  const phase = ref<TransferPhase>('pick')
  const fileName = ref('')
  const fileSize = ref(0)
  const progress = ref(0)
  const error = ref('')
  const plan = shallowRef<P | null>(null)
  const choices = ref<Record<string, TransferChoice>>({})
  const planChanged = ref(false)
  const report = shallowRef<R | null>(null)

  const uploadId = ref('')
  let aborter: AbortController | null = null
  // Each start is a run of its own; `discard` begins a new one. An answer arriving for a run that
  // is no longer the current one — the person cancelled, closed the window, chose another file —
  // changes nothing on screen: it would bring a dead plan or an «aborted» text into the window.
  let run = 0

  const ready = computed(() =>
    phase.value === 'plan' && Boolean(uploadId.value) && plan.value !== null && allChosen(plan.value.conflicts, choices.value))
  const busy = computed(() => phase.value === 'upload' || phase.value === 'analyze' || phase.value === 'apply')

  async function start(file: File): Promise<void> {
    await discard()
    const mine = ++run
    phase.value = 'upload'
    fileName.value = file.name
    fileSize.value = file.size
    progress.value = 0
    planChanged.value = false
    const controller = new AbortController()
    aborter = controller
    let taken = ''
    try {
      const upload = await api.upload(
        file,
        (loaded, total) => { if (mine === run) progress.value = total > 0 ? Math.round((loaded / total) * 100) : 0 },
        controller.signal,
      )
      taken = upload.upload_id
      if (mine !== run) {
        // The upload finished on the server after all: give it back, nobody will import it.
        await api.cancel(taken).catch(() => undefined)
        return
      }
      uploadId.value = taken
      fileName.value = upload.file_name
      fileSize.value = upload.size
      phase.value = 'analyze'
      const read = await api.analyze(taken)
      if (mine !== run) return
      plan.value = read
      choices.value = presetChoices(read.conflicts)
      phase.value = 'plan'
    } catch (e) {
      if (mine !== run || controller.signal.aborted) return
      const reason = errorText(e)
      await discard()
      error.value = reason
    } finally {
      if (aborter === controller) aborter = null
    }
  }

  function pick(id: string, value: TransferChoice): void {
    if (!plan.value) return
    choices.value = choose(plan.value.conflicts, choices.value, id, value)
  }

  function pickAll(value: TransferChoice): void {
    if (!plan.value) return
    choices.value = chooseAll(plan.value.conflicts, value)
  }

  /** Apply; the report on success, `null` when the import did not happen (the reason is in `error`). */
  async function apply(): Promise<R | null> {
    if (!plan.value || !uploadId.value || !ready.value) return null
    phase.value = 'apply'
    error.value = ''
    try {
      const done = await api.apply(uploadId.value, choices.value, plan.value.plan_token)
      uploadId.value = ''
      report.value = done
      phase.value = 'done'
      return done
    } catch (e) {
      if (e instanceof ApiError && e.code === PLAN_CHANGED) {
        try {
          const read = await api.analyze(uploadId.value)
          choices.value = carriedChoices(read.conflicts, choices.value)
          plan.value = read
          planChanged.value = true
          phase.value = 'plan'
          return null
        } catch (again) {
          error.value = errorText(again)
        }
      } else {
        error.value = errorText(e)
      }
      phase.value = 'plan'
      return null
    }
  }

  /** Back to choosing a file, nothing of the last one left on screen; the uploaded one is given back. */
  async function discard(): Promise<void> {
    run += 1
    aborter?.abort()
    aborter = null
    const abandoned = uploadId.value
    uploadId.value = ''
    plan.value = null
    choices.value = {}
    report.value = null
    planChanged.value = false
    error.value = ''
    progress.value = 0
    if (phase.value !== 'pick') phase.value = 'pick'
    // The cancel itself is no news to the person: its refusal is not shown.
    if (abandoned) await api.cancel(abandoned).catch(() => undefined)
  }

  return {
    phase,
    fileName,
    fileSize,
    progress,
    error,
    plan,
    choices,
    planChanged,
    report,
    ready,
    busy,
    start,
    pick,
    pickAll,
    apply,
    discard,
  }
}
