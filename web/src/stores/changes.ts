import { ref } from 'vue'
import { defineStore } from 'pinia'

import { CLIENT_ID } from '@/api/client/client-id'

// Лента изменений данных — фронтовая половина модуля `core_changes`.
//
// Лежит в основании (`stores/`), а не модулем в `features/`: на неё подписываются разные модули
// (задачи, группы, дальше — другие), а модуль не может импортировать модуль
// (`tests/apps/test_web_layer_boundaries.py`). Сущностей она не знает — знать ей нечего.
//
// ЭХО СВОИХ ПРАВОК подписчикам не раздаётся. Каждое сообщение несёт `origin` — id вкладки, чей
// запрос его вызвал (`api/client/client-id.ts`). Своё сохранение экран уже учёл по ответу на
// запрос, а событие о нём приходит РАНЬШЕ этого ответа (бэк шлёт его сразу после коммита):
// раздай его подписчику — страница задачи увидела бы «в базе поле изменилось, а у меня оно
// правлено» и открыла бы ложный конфликт на собственную правку. Индикатору в углу своё
// показывается — он про «что обновилось», а не про «что перечитать».
//
// Одно соединение на всё приложение: бэк держит открытый SSE-поток и шлёт в него, какие
// объявленные сущности созданы, изменены или удалены. Сам стор про сущности ничего не знает —
// он принимает сообщения и раздаёт их тем, кто подписался на нужную сущность (`on`). Что делать с
// изменением — перечитать список, карточку, ничего, — решает подписчик.
//
// Пропущенное за обрыв не досылается: бэк ничего не хранит. Поэтому каждое ПЕРЕподключение
// (и кадр `resync`, когда вкладка отстала) раздаётся подписчикам `onResync` — «перечитай то, что у
// тебя на экране»; первое подключение — нет: экраны и так только что загрузились.

/** Что случилось с сущностью. Имена — контракт с бэком (`core_changes/capture.py`). */
export type ChangeEvent = 'created' | 'updated' | 'deleted'

/**
 * Одно изменение: сущность, событие, коды затронутых и коды тех, к кому они относятся.
 *
 * Пустой `ids` — массовая операция без названных кодов: подписчик перечитывает всё своё.
 * `refs` — по ним экран понимает «это про меня», не зная, что за сущность пришла (у этапа там его
 * задача).
 */
export interface Change {
  entity: string
  event: ChangeEvent
  ids: string[]
  refs: string[]
  /** Правку сделала эта же вкладка. Подписчики таких не получают; индикатор — получает. */
  own: boolean
}

/** Сообщение ленты: одна транзакция бэка. `origin` — id вкладки-источника или `null`. */
interface ChangesMessage {
  origin: string | null
  changes: Omit<Change, 'own'>[]
}

export type ChangeHandler = (change: Change) => void

/** Случай ленты: изменение или — при `change: null` — «перечитай всё» (переподключение, отставание). */
export interface ChangeSignal {
  seq: number
  change: Change | null
}

/** Подписка на все сущности разом — для отладки и журнала, а не для экранов. */
export const ANY_ENTITY = '*'

const STREAM_URL = '/internal/core/changes/stream'

/** Сколько последних изменений держим для показа; ленте это история на один взгляд, не журнал. */
const RECENT_LIMIT = 50

export const useChangesStore = defineStore('changes', () => {
  const connected = ref(false)
  const recent = ref<Change[]>([])
  // Последний случай ленты — для индикатора в углу (`ChangesIndicator`). `seq` растёт на каждый:
  // два одинаковых изменения подряд — два случая, и второй тоже должен показаться.
  const latest = ref<ChangeSignal | null>(null)
  let seq = 0

  const handlers = new Map<string, Set<ChangeHandler>>()
  const resyncHandlers = new Set<() => void>()

  let source: EventSource | null = null
  let everConnected = false

  /** Поднять соединение. Повторный вызов ничего не делает: поток один на приложение. */
  function connect(): void {
    if (source) return
    source = new EventSource(STREAM_URL)

    source.onopen = () => {
      connected.value = true
      // Переподключение — не первое открытие: пока нас не было, что-то могло поменяться.
      if (everConnected) resync()
      everConnected = true
    }

    // Обрыв браузер чинит сам (пауза из кадра `retry`); здесь только отмечаем, что мы без связи.
    source.onerror = () => {
      connected.value = false
    }

    source.addEventListener('changes', (event) => {
      const payload = JSON.parse((event as MessageEvent<string>).data) as ChangesMessage
      const own = payload.origin !== null && payload.origin === CLIENT_ID
      for (const change of payload.changes) dispatch({ ...change, own })
    })

    source.addEventListener('resync', resync)
  }

  function disconnect(): void {
    source?.close()
    source = null
    connected.value = false
  }

  function dispatch(change: Change): void {
    recent.value = [change, ...recent.value].slice(0, RECENT_LIMIT)
    latest.value = { seq: ++seq, change }
    if (change.own) return
    for (const key of [change.entity, ANY_ENTITY]) {
      for (const handler of handlers.get(key) ?? []) handler(change)
    }
  }

  function resync(): void {
    latest.value = { seq: ++seq, change: null }
    for (const handler of resyncHandlers) handler()
  }

  /**
   * Подписаться на изменения сущности (`tasks.task`) или всех сразу (`ANY_ENTITY`). Возвращает
   * отписку — звать её при размонтировании подписчика, иначе обработчик переживёт свой экран.
   */
  function on(entity: string, handler: ChangeHandler): () => void {
    let bucket = handlers.get(entity)
    if (!bucket) handlers.set(entity, (bucket = new Set()))
    bucket.add(handler)
    return () => bucket.delete(handler)
  }

  /** Подписаться на «перечитай всё»: переподключение после обрыва и отставание вкладки. */
  function onResync(handler: () => void): () => void {
    resyncHandlers.add(handler)
    return () => resyncHandlers.delete(handler)
  }

  /** Сколько обработчиков сейчас подписано — для проверки, что экраны отписываются. */
  function subscriberCount(): number {
    let total = resyncHandlers.size
    for (const bucket of handlers.values()) total += bucket.size
    return total
  }

  return { connected, recent, latest, connect, disconnect, on, onResync, subscriberCount }
})
