import { ref } from 'vue'
import { defineStore } from 'pinia'

import { errorText } from '@/api/errorText'

import {
  deleteTask,
  getTask,
  purgeTask,
  restoreTask,
  setTaskStatus,
  updateTask,
  type TaskDetail,
  type TaskUpdateBody,
} from '../api'

// Деталка задачи: карточка, тело в markdown и дети. Дерево страница не строит — ей хватает
// одного уровня вниз (`children`) и ссылки вверх (`parent_code`): дальше человек идёт переходами,
// а не разглядывает всю ветку сразу.
export const useTaskDetailStore = defineStore('tasks-task-detail', () => {
  const task = ref<TaskDetail | null>(null)
  const loading = ref(false)
  // Держим сам отказ, а не его текст: показ (`SectionError`) отличает «задачи нет» от сбоя по
  // статусу ответа, а формулировку берёт из `errorText`.
  const error = ref<unknown>(null)
  // Операция в полёте (статус, удаление, восстановление) — заперты кнопки, а не вся страница.
  const busy = ref(false)
  // Правка полей едет сама, без кнопки, поэтому у неё своя пара: чем она занята сейчас и чем
  // кончилась прошлая попытка. `busy` тут не годится — он запирает кнопки, а поле, в котором
  // человек продолжает печатать, запирать нельзя.
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  // Код задачи, которую сейчас ждём: ответ на устаревший запрос не должен перебить пришедший
  // позже, если человек успел уйти на другую задачу.
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
   * Правка полей карточки. Бэк принимает карточку ЦЕЛИКОМ (не переданное поле стирается), поэтому
   * изменённые поля накладываются на то, что уже показано, и уезжают все вместе.
   *
   * Ответ кладём в `task`: вместе с полями он несёт новую отметку изменения, и перечитывать
   * задачу отдельным запросом после каждой правки незачем. Отказ не откатывает поля на экране —
   * набранное остаётся на месте, чтобы его можно было отправить ещё раз.
   */
  async function patch(fields: Partial<TaskUpdateBody>): Promise<boolean> {
    const row = task.value
    if (!row) return false

    const body: TaskUpdateBody = {
      title: row.title,
      description: row.description,
      context: row.context,
      constraints: row.constraints,
      criteria: row.criteria,
      body: row.body,
      type: row.type,
      priority: row.priority,
      group_code: row.group_code,
      deadline_at: row.deadline_at,
      ...fields,
    }

    saving.value = true
    saveError.value = null
    try {
      // `report: false` — о неудавшейся правке говорит сама карточка, рядом с полями: тост о
      // запросе, которого человек не запускал руками, читается как сбой неизвестно чего.
      task.value = await updateTask(row.code, body, { report: false })
      return true
    } catch (e) {
      saveError.value = errorText(e)
      return false
    } finally {
      saving.value = false
    }
  }

  /**
   * Смена статуса — отдельная ручка: вместе со статусом бэк ставит отметку фазы (начало,
   * завершение, отмена), и общая правка карточки его не трогает вовсе.
   *
   * Ответ — задача целиком, поэтому перечитывать страницу после не нужно: пришедшая карточка уже
   * несёт и новые отметки времени.
   */
  async function changeStatus(status: string) {
    const code = task.value?.code
    if (!code || status === task.value?.status) return
    busy.value = true
    try {
      task.value = await setTaskStatus(code, status)
    } catch {
      // Об отказе сказал тост клиента; статус на экране остаётся прежним — то есть тем, что в базе.
    } finally {
      busy.value = false
    }
  }

  /** Мягкое удаление — вместе с веткой. Задача остаётся на экране: её можно вернуть отсюда же. */
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
   * Физическое удаление: возвращать будет некуда, поэтому страница после успеха уходит в список —
   * решение об уходе принимает она, стор только сообщает, удалось ли.
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
