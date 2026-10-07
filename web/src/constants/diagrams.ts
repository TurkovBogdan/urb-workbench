// Styling of diagrams in a document body. The diagram typeface lives next door, in
// `constants/fonts.ts` (`DIAGRAM_FONTS`): it belongs to the font setup, while this file holds the
// layout of the diagram block.

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

// Diagram palette. "System" is not a palette but the absence of one: colours go into the SVG as
// references to the app's tokens, so the diagram follows the theme and switches with it without a
// re-render. The rest are the engine's ready-made palettes (`THEMES` from `beautiful-mermaid`):
// each has its own background and no longer depends on whether the app theme is light or dark.
//
// The list of codes is kept here rather than taken from the engine: the engine arrives as a
// separate 1.5 MB chunk with the first diagram on a page, and importing it for the names would
// drag it into the main bundle. The diagram block itself resolves colours by code — after the
// engine has loaded; an unknown code falls back to the system colours there.
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

// Maximum diagram height in the body, in pixels. A diagram here illustrates the text, and a tall
// one pushes off screen what the page was opened for; it is examined in fullscreen mode.
// `0` — no cap: the diagram is shown whole, however long it is.
export const DIAGRAM_HEIGHTS = [280, 420, 560, 0] as const

export const DEFAULT_DIAGRAM_HEIGHT = 420

export const NO_DIAGRAM_HEIGHT = 0

// An unknown value (a stale localStorage key, an option dropped from the set) falls back to the
// default rather than leaving the block without alignment.
export function diagramAlign(code: string): DiagramAlign {
  return DIAGRAM_ALIGNS.some((option) => option.code === code)
    ? (code as DiagramAlign)
    : DEFAULT_DIAGRAM_ALIGN
}
