// Поведение без собственного интерфейса: расширения и композаблы, которые ничего не рисуют
// сами, а меняют то, что документ делает в ответ на действие.
//
// Граница с `controls/` проходит по видимости: здесь нет ни одной кнопки и ни одного меню —
// только реакция на клавиши, вставку и перетаскивание. Всё, что видно на экране, живёт либо
// декорацией (подсветка исходника переноса, вспышка после перемещения), либо в `controls/`.
export { BlockMoves, type MoveTarget } from './blockMoves'
export { DragSource } from './dragSource'
export { MarkdownPaste } from './markdownPaste'
export { useDragPreview, type DragPreview } from './useDragPreview'
