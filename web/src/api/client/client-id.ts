// Id этой вкладки для ленты изменений (`core_changes`).
//
// Каждый запрос к своему бэку несёт его в `X-Client-Id`; бэк ставит его в сообщение ленты как
// `origin`, и вкладка узнаёт эхо собственных сохранений (`stores/changes.ts`). Живёт до перезагрузки
// страницы и нигде не хранится: две вкладки — два источника, иначе правка из одной считалась бы
// «своей» во второй, и та её не увидела бы.
export const CLIENT_ID_HEADER = 'X-Client-Id'

// `randomUUID` есть только в защищённом контексте (https, localhost); открытая по адресу в сети
// по http вкладка получила бы исключение на старте. Уникальности на время жизни вкладки хватает
// и от запасного пути.
export const CLIENT_ID: string =
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
