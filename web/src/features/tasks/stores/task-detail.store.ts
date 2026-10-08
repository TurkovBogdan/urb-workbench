import { ref } from 'vue'
import { defineStore } from 'pinia'

import { errorText } from '@/api/errorText'

import {
  deleteTask,
  getTask,
  patchTask,
  purgeTask,
  restoreTask,
  setTaskStatus,
  type TaskDetail,
  type TaskUpdateBody,
} from '../api'

// Task detail: the card, the brief and the agent's work in markdown, and the children. The page builds no tree — one level
// down (`children`) and a link up (`parent_code`) are enough: beyond that the person navigates
// rather than surveying the whole branch at once.
export const useTaskDetailStore = defineStore('tasks-task-detail', () => {
  const task = ref<TaskDetail | null>(null)
  const loading = ref(false)
  // Keep the failure itself, not its text: the display (`SectionError`) tells "no such task" from
  // a fault by the response status, and takes the wording from `errorText`.
  const error = ref<unknown>(null)
  // An operation in flight (status, delete, restore) — the buttons are locked, not the whole page.
  const busy = ref(false)
  // Field edits are sent on their own, without a button, so they have their own pair: what is in
  // progress now and how the last attempt ended. `busy` will not do here — it locks the buttons,
  // and a field the person keeps typing into must not be locked.
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  // Code of the task we are waiting for: a response to a stale request must not override a later
  // one if the person has already moved to another task.
  let current = ''

  async function load(code: string) {
    current = code
    loading.value = true
    error.value = null
    saveError.value = null
    try {
      const data = await getTask(code)
      if (current !== code) return
      task.value = data
    } catch (e) {
      if (current !== code) return
      error.value = e
      task.value = null
    } finally {
      if (current === code) loading.value = false
    }
  }

  /**
   * Edit card fields — ONLY the named ones (`PATCH`). The other fields are not sent at all: while
   * the page is open the agent may have changed them, and a full card assembled from what the
   * page once loaded would roll back the agent's edit.
   *
   * The response goes into `task`: along with the fields it carries the new modification stamp,
   * so there is no need to re-read the task with a separate request after each edit. A refusal
   * does not roll back the fields on screen — what was typed stays so it can be sent again.
   */
  async function patch(fields: Partial<TaskUpdateBody>): Promise<boolean> {
    const row = task.value
    if (!row) return false

    saving.value = true
    saveError.value = null
    try {
      // `report: false` — a failed edit is reported by the card itself, next to the fields: a toast
      // about a request the person did not launch by hand reads as a failure of who knows what.
      task.value = await patchTask(row.code, fields, { report: false })
      return true
    } catch (e) {
      saveError.value = errorText(e)
      return false
    } finally {
      saving.value = false
    }
  }

  /**
   * Status change is a separate endpoint: together with the status the backend stamps the phase
   * (start, completion, cancel), and the general card update does not touch status at all.
   *
   * The response is the whole task, so there is no need to re-read the page afterwards: the
   * returned card already carries the new timestamps.
   */
  async function changeStatus(status: string) {
    const code = task.value?.code
    if (!code || status === task.value?.status) return
    busy.value = true
    try {
      task.value = await setTaskStatus(code, status)
    } catch {
      // The client's toast reported the refusal; the status on screen stays as it was — i.e. as in
      // the database.
    } finally {
      busy.value = false
    }
  }

  /** Soft delete — together with the branch. The task stays on screen: it can be restored here. */
  async function remove(): Promise<boolean> {
    const code = task.value?.code
    if (!code) return false
    busy.value = true
    try {
      await deleteTask(code)
      await load(code)
      return true
    } catch {
      return false
    } finally {
      busy.value = false
    }
  }

  async function restore(): Promise<boolean> {
    const code = task.value?.code
    if (!code) return false
    busy.value = true
    try {
      task.value = await restoreTask(code)
      return true
    } catch {
      return false
    } finally {
      busy.value = false
    }
  }

  /**
   * Physical deletion: there will be nothing to come back to, so on success the page leaves for
   * the list — the page decides to leave, the store only reports whether it succeeded.
   */
  async function purge(): Promise<boolean> {
    const code = task.value?.code
    if (!code) return false
    busy.value = true
    try {
      await purgeTask(code)
      task.value = null
      return true
    } catch {
      return false
    } finally {
      busy.value = false
    }
  }

  return {
    task, loading, error, busy, saving, saveError,
    load, patch, changeStatus, remove, restore, purge,
  }
})
