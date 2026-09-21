// Видимый хром редактора: панель над выделением и меню по слэшу.
//
// Всё здесь нарисовано из компонентов приложения. Tiptap отдаёт открытым ядро — схему,
// транзакции, ручку драга, механику подсказок, — а собранный интерфейс продаёт; взять ядро и
// нарисовать хром из Vuetify стоит тулбара и списка, зато редактор остаётся внутри темы
// приложения, а не рядом со второй дизайн-системой.
export { default as BubbleToolbar } from './BubbleToolbar.vue'
export { default as SlashMenuPopup } from './SlashMenuPopup.vue'
export { default as TableControls } from './TableControls.vue'
export {
  SlashMenuExtension,
  createSlashItems,
  shortcutLabels,
  useSlashMenu,
  type SlashItem,
  type SlashMenu,
  type SlashController,
  type SlashState,
} from './slashMenu'
