import { IconFolders, IconTable } from '@tabler/icons-vue'
import type { FunctionalComponent } from 'vue'

// How to show the list of researches. Table by default: a research has five numeric counters, and
// columns are the only layout in which they can be compared across rows. Tiles are always grouped
// by shelf: on their own they produced a flat stream that the table shows more densely with the
// same data, so what tiles are needed for is exactly the shelf breakdown.

export type ResearchListView = 'table' | 'grouped'

export const DEFAULT_RESEARCH_LIST_VIEW: ResearchListView = 'table'

export interface ResearchListViewOption {
  code: ResearchListView
  /** i18n key: the tooltip on the page's toggle. */
  label: string
  icon: FunctionalComponent
}

export const RESEARCH_LIST_VIEWS: ResearchListViewOption[] = [
  { code: 'table', label: 'research.list_view.table', icon: IconTable },
  { code: 'grouped', label: 'research.list_view.grouped', icon: IconFolders },
]
