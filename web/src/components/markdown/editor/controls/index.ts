// The editor's visible chrome: the toolbar over a selection and the slash menu.
//
// Everything here is drawn from the app's own components. Tiptap open-sources the core — schema,
// transactions, drag handle, suggestion mechanics — and sells the assembled UI; taking the core
// and drawing the chrome from Vuetify costs a toolbar and a list, but keeps the editor inside the
// app's theme instead of next to a second design system.
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
