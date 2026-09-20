/**
 * Клиент API модуля workspace (бэк: /internal/workspace).
 *
 * Пространство — верхний уровень изоляции данных: модули поверх (задачи сегодня, документация
 * завтра) сужают свои списки до того, что выбрано в панели. Поэтому и модуль, и эта папка стоят
 * отдельно от них: зависимость идёт снизу вверх и только в одну сторону.
 *
 * Коды приходят с префиксом (WORKSPACE@…) и в таком же виде уезжают обратно: бэк снимает
 * префикс сам, а в сегмент адреса он кодируется через `encodeURIComponent` — «@» в пути
 * разрешён, но кодирование безопаснее для любых будущих форм кода.
 *
 * Даты — SQL-формат (dto.py::DatetimeUTCStr), форматирует shared/utils/date.
 */

import { internalApi, type RequestOptions } from '@/api/client/internal'

const BASE = '/workspace'

const seg = (code: string) => encodeURIComponent(code)

export interface WorkspaceRow {
  code: string
  title: string
  description: string
  /** Имя из реестра `shared/colors.ts`; пустое — цвет не выбран, рисуем акцентом. */
  color: string
  /** Имя из реестра `shared/icons.ts`; пустое — иконка не выбрана, рисуем запасную. */
  icon: string
  created_at: string
  updated_at: string
  /** Не null — пространство в корзине: правка ему недоступна, доступны восстановление и снос. */
  deleted_at: string | null
}

/**
 * Счётчик содержимого: чей он, как его подписать и сколько насчиталось.
 *
 * Набор счётчиков не фиксирован — его объявляют модули поверх (`workspace.stats` на бэке), и
 * зависит он от состава приложения. Подпись приезжает КЛЮЧОМ сообщения: владеет ею модуль,
 * которому принадлежит сущность, и текст лежит в его словаре, а не в нашем.
 */
export interface WorkspaceCounter {
  key: string
  label_key: string
  count: number
}

export interface WorkspaceListRow extends WorkspaceRow {
  counters: WorkspaceCounter[]
}

export interface WorkspaceBody {
  title: string
  description: string
  color: string
  icon: string
}

export interface ListWorkspacesParams {
  /** Показать и удалённые — переключатель в шапке списка. */
  include_deleted?: boolean
}

export async function listWorkspaces(
  params: ListWorkspacesParams = {},
  opts?: RequestOptions,
): Promise<WorkspaceListRow[]> {
  return internalApi.get<WorkspaceListRow[]>(BASE, { ...opts, query: { ...params } })
}

export async function getWorkspace(
  code: string,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.get<WorkspaceRow>(`${BASE}/${seg(code)}`, opts)
}

export async function createWorkspace(
  body: WorkspaceBody,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.post<WorkspaceRow>(BASE, body, opts)
}

export async function updateWorkspace(
  code: string,
  body: WorkspaceBody,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.put<WorkspaceRow>(`${BASE}/${seg(code)}`, body, opts)
}

/** Мягкое удаление: содержимое остаётся, вернуть можно `restoreWorkspace`. */
export async function deleteWorkspace(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/${seg(code)}`, undefined, opts)
}

export async function restoreWorkspace(
  code: string,
  opts?: RequestOptions,
): Promise<WorkspaceRow> {
  return internalApi.post<WorkspaceRow>(`${BASE}/${seg(code)}/restore`, undefined, opts)
}

/**
 * Физическое удаление: пространство исчезает вместе со всем, что держали в нём модули поверх, —
 * вернуть нечего. Отдельная функция, а не флаг у `deleteWorkspace`, ровно как на бэке:
 * необратимое не должно отличаться от обратимого одним аргументом на месте вызова.
 */
export async function purgeWorkspace(code: string, opts?: RequestOptions): Promise<void> {
  await internalApi.del<void>(`${BASE}/${seg(code)}/purge`, undefined, opts)
}
