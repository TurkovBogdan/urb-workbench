import { IconFolders, IconTable } from '@tabler/icons-vue'
import type { FunctionalComponent } from 'vue'

// Как показывать список исследований. Таблица по умолчанию: у исследования пять числовых
// счётчиков, а колонки — единственная раскладка, в которой их можно сравнить между строками.
// Плитки — всегда по полкам: сами по себе они давали общий поток, который таблица показывает
// плотнее и с теми же данными, поэтому от плиток нужен ровно состав полок.

export type ResearchListView = 'table' | 'grouped'

export const DEFAULT_RESEARCH_LIST_VIEW: ResearchListView = 'table'

export interface ResearchListViewOption {
  code: ResearchListView
  /** Ключ i18n: всплывающая подпись у переключателя на странице. */
  label: string
  icon: FunctionalComponent
}

export const RESEARCH_LIST_VIEWS: ResearchListViewOption[] = [
  { code: 'table', label: 'research.list_view.table', icon: IconTable },
  { code: 'grouped', label: 'research.list_view.grouped', icon: IconFolders },
]
