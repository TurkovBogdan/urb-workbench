// Оформление схем в теле документа. Гарнитура схем живёт рядом, в `constants/fonts.ts`
// (`DIAGRAM_FONTS`): она часть шрифтового хозяйства, а здесь — раскладка блока со схемой.

export type DiagramAlign = 'left' | 'center'

// Label and note come from the dictionary by code (`composables/useAppearanceOptions.ts`).
export interface DiagramAlignOption {
  code: DiagramAlign
}

export const DIAGRAM_ALIGNS: DiagramAlignOption[] = [
  { code: 'left' },
  { code: 'center' },
]

export const DEFAULT_DIAGRAM_ALIGN: DiagramAlign = 'left'

// Палитра схемы. «Системная» — не палитра, а отказ от неё: цвета уезжают в SVG ссылками на токены
// приложения, поэтому схема следует за темой и переключается вместе с ней без перерисовки.
// Остальное — готовые палитры движка (`THEMES` из `beautiful-mermaid`): у каждой свой фон, и она
// уже не зависит от того, светлая тема в приложении или тёмная.
//
// Список кодов держим здесь, а не берём из движка: он приезжает отдельным чанком в полтора
// мегабайта по первой схеме на странице, и импорт ради названий притащил бы его в общий бандл.
// Цвета по коду достаёт сам блок схемы — уже после загрузки движка; неизвестный код там
// откатывается к системным цветам.
export const SYSTEM_DIAGRAM_THEME = 'system'

// A palette name is a proper noun and stays here; the note — and the label of `system`, which is
// not a palette — come from the dictionary by code (`composables/useAppearanceOptions.ts`).
export interface DiagramThemeOption {
  code: string
  label?: string
}

export const DIAGRAM_THEMES: DiagramThemeOption[] = [
  { code: SYSTEM_DIAGRAM_THEME },
  { code: 'zinc-light', label: 'Zinc Light' },
  { code: 'zinc-dark', label: 'Zinc Dark' },
  { code: 'github-light', label: 'GitHub Light' },
  { code: 'github-dark', label: 'GitHub Dark' },
  { code: 'tokyo-night', label: 'Tokyo Night' },
  { code: 'tokyo-night-storm', label: 'Tokyo Night Storm' },
  { code: 'tokyo-night-light', label: 'Tokyo Night Light' },
  { code: 'catppuccin-mocha', label: 'Catppuccin Mocha' },
  { code: 'catppuccin-latte', label: 'Catppuccin Latte' },
  { code: 'nord', label: 'Nord' },
  { code: 'nord-light', label: 'Nord Light' },
  { code: 'dracula', label: 'Dracula' },
  { code: 'solarized-light', label: 'Solarized Light' },
  { code: 'solarized-dark', label: 'Solarized Dark' },
  { code: 'one-dark', label: 'One Dark' },
]

export const DEFAULT_DIAGRAM_THEME = SYSTEM_DIAGRAM_THEME

export function diagramTheme(code: string): string {
  return DIAGRAM_THEMES.some((option) => option.code === code) ? code : DEFAULT_DIAGRAM_THEME
}

// Потолок высоты схемы в теле, в пикселях. Схема здесь — иллюстрация к тексту, и высокая
// вытесняет с экрана то, ради чего её открыли; разглядывают её в полноэкранном режиме.
// `0` — без потолка: схема показывается целиком, какой бы длинной ни была.
export const DIAGRAM_HEIGHTS = [280, 420, 560, 0] as const

export const DEFAULT_DIAGRAM_HEIGHT = 420

export const NO_DIAGRAM_HEIGHT = 0

// Неизвестное значение (устаревший ключ в localStorage, выпавший из набора вариант) откатывается
// к умолчанию, а не оставляет блок без выравнивания.
export function diagramAlign(code: string): DiagramAlign {
  return DIAGRAM_ALIGNS.some((option) => option.code === code)
    ? (code as DiagramAlign)
    : DEFAULT_DIAGRAM_ALIGN
}
