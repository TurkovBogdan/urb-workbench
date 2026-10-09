// Font families offered in interface settings, in two independent roles.
//
// The split is the point: interface text is scanned in small sizes (table rows, list
// items, labels) while a research body is read continuously, and the two roles want
// different families as well as different sizes. The chosen stacks reach CSS as the
// `--font` and `--font-reading` tokens (see stores/settings.ts).
//
// A bundled family must have a matching @font-face in styles/fonts.scss; the system
// entries deliberately have none — they resolve to whatever the OS provides.

// A family name is a proper noun and stays here. The note under the option — the reason to pick
// it — and the label of the system entries, which are descriptions rather than names, come from
// the dictionary by code (`composables/useAppearanceOptions.ts`).
export interface FontOption {
  code: string
  label?: string
  // The complete CSS font-family value, fallbacks included.
  stack: string
}

const SANS_FALLBACK = 'system-ui, -apple-system, "Segoe UI", sans-serif'
const SERIF_FALLBACK = 'Georgia, "Times New Roman", serif'
const MONO_FALLBACK = 'ui-monospace, SFMono-Regular, Consolas, monospace'

const ONEST: FontOption = {
  code: 'onest',
  label: 'Onest',
  stack: `'Onest', ${SANS_FALLBACK}`,
}

const GOLOS: FontOption = {
  code: 'golos',
  label: 'Golos Text',
  stack: `'Golos Text', ${SANS_FALLBACK}`,
}

const IBM_PLEX_SANS: FontOption = {
  code: 'ibm-plex-sans',
  label: 'IBM Plex Sans',
  stack: `'IBM Plex Sans', ${SANS_FALLBACK}`,
}

const PT_SANS: FontOption = {
  code: 'pt-sans',
  label: 'PT Sans',
  stack: `'PT Sans', ${SANS_FALLBACK}`,
}

const COMMISSIONER: FontOption = {
  code: 'commissioner',
  label: 'Commissioner',
  stack: `'Commissioner', ${SANS_FALLBACK}`,
}

const GEOLOGICA: FontOption = {
  code: 'geologica',
  label: 'Geologica',
  stack: `'Geologica', ${SANS_FALLBACK}`,
}

const LITERATA: FontOption = {
  code: 'literata',
  label: 'Literata',
  stack: `'Literata', ${SERIF_FALLBACK}`,
}

const PT_SERIF: FontOption = {
  code: 'pt-serif',
  label: 'PT Serif',
  stack: `'PT Serif', ${SERIF_FALLBACK}`,
}

const SOURCE_SERIF: FontOption = {
  code: 'source-serif',
  label: 'Source Serif',
  stack: `'Source Serif', ${SERIF_FALLBACK}`,
}

const LORA: FontOption = {
  code: 'lora',
  label: 'Lora',
  stack: `'Lora', ${SERIF_FALLBACK}`,
}

const PIAZZOLLA: FontOption = {
  code: 'piazzolla',
  label: 'Piazzolla',
  stack: `'Piazzolla', ${SERIF_FALLBACK}`,
}

const SPECTRAL: FontOption = {
  code: 'spectral',
  label: 'Spectral',
  stack: `'Spectral', ${SERIF_FALLBACK}`,
}

const JETBRAINS_MONO: FontOption = {
  code: 'jetbrains-mono',
  label: 'JetBrains Mono',
  stack: `'JetBrains Mono', ${MONO_FALLBACK}`,
}

const IBM_PLEX_MONO: FontOption = {
  code: 'ibm-plex-mono',
  label: 'IBM Plex Mono',
  stack: `'IBM Plex Mono', ${MONO_FALLBACK}`,
}

const MARTIAN_MONO: FontOption = {
  code: 'martian-mono',
  label: 'Martian Mono',
  stack: `'Martian Mono', ${MONO_FALLBACK}`,
}

const SYSTEM_MONO: FontOption = {
  code: 'system-mono',
  stack: MONO_FALLBACK,
}

const SYSTEM_SANS: FontOption = {
  code: 'system',
  stack: SANS_FALLBACK,
}

const SYSTEM_SERIF: FontOption = {
  code: 'system-serif',
  stack: SERIF_FALLBACK,
}

export const INTERFACE_FONTS: FontOption[] = [
  ONEST,
  GOLOS,
  IBM_PLEX_SANS,
  PT_SANS,
  COMMISSIONER,
  GEOLOGICA,
  SYSTEM_SANS,
]

// Serifs come first: the reading role is long text, and this is exactly where serifs belong.
export const READING_FONTS: FontOption[] = [
  LITERATA,
  PT_SERIF,
  SOURCE_SERIF,
  LORA,
  PIAZZOLLA,
  SPECTRAL,
  ONEST,
  GOLOS,
  IBM_PLEX_SANS,
  PT_SANS,
  SYSTEM_SERIF,
  SYSTEM_SANS,
]

// "Same as text" is not a typeface but declining to choose: headings are set in whatever the text
// is set in, and follow it when it changes. The stack is a reference to its token, so the list row
// is rendered in the current choice, and in CSS the value is substituted without a branch in code.
const HEADING_AS_READING: FontOption = {
  code: 'reading',
  stack: 'var(--font-reading)',
}

// Headings take either the text font or their own — from the same set as the reading zone: a
// heading lives in the same document, and families unfit for continuous reading are unfit here too.
export const HEADING_FONTS: FontOption[] = [HEADING_AS_READING, ...READING_FONTS]

// Code is its own role: monospace in code blocks, inline chips and technical captions
// (`--font-mono`). It is not offered for diagrams: the layout measures labels with proportional
// letter widths, and a monospace line is wider — it would overflow the boxes.
export const MONO_FONTS: FontOption[] = [JETBRAINS_MONO, IBM_PLEX_MONO, MARTIAN_MONO, SYSTEM_MONO]

// Diagrams are the third role: a label inside a box lives in a tight space, and the renderer
// measures it with the selected typeface. Hence the set: only tightly drawn sans-serifs — serif
// and monospace faces set the label wider than the box was sized for.
export const DIAGRAM_FONTS: FontOption[] = [ONEST, GOLOS, IBM_PLEX_SANS, PT_SANS, SYSTEM_SANS]

export const DEFAULT_INTERFACE_FONT = ONEST.code
export const DEFAULT_READING_FONT = ONEST.code
export const DEFAULT_HEADING_FONT = HEADING_AS_READING.code
export const DEFAULT_MONO_FONT = JETBRAINS_MONO.code
export const DEFAULT_DIAGRAM_FONT = ONEST.code

// Base size of the reading zone in pixels. Everything inside a body is sized in `em` off
// this one value, so a step moves the whole prose scale — headings, code, tables, indents —
// and not just the paragraphs. The floor is the lower bound for continuous reading; the
// ceiling is where a line stops fitting the column on a laptop screen.
export const READING_SIZES = [14, 15, 16, 17, 18, 20] as const

export const DEFAULT_READING_SIZE = 14

// Weight of the reading zone — the full CSS scale, 100 to 900. Headings and emphasis in the body
// don't follow it: they have their own weight, otherwise the difference between the text and the
// emphasis within it would vanish along with the choice.
//
// A caveat about the low end: not every bundled family has faces lighter than regular
// (PT Sans, PT Serif, Spectral and IBM Plex Mono have none at all, Golos Text's axis starts
// at 400) — there the browser takes the nearest available, and 100–300 render as 400.
export const READING_WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900] as const

export const DEFAULT_READING_WEIGHT = 300

// Headings use the same scale but a separate choice: the difference between them and the text is
// exactly what makes the section structure readable, and it has to be kept paired with the text
// weight.
export const DEFAULT_HEADING_WEIGHT = 600

// Font size of a code block in a document body, in pixels. Its own ladder and its own choice:
// monospace at the same size looks larger than proportional type, and a listing set level with the
// text pulls attention to itself. Line numbers and padding inside the block are in `em` and follow.
export const CODE_SIZES = [11, 12, 13, 14, 15, 16] as const

export const DEFAULT_CODE_SIZE = 12

// Width of the running-text column, in `ch`. Tables, code blocks and images are outside it —
// they are scanned rather than read line by line, and squeezing them into the text column only
// makes them scroll. `0` means no cap at all: the text runs to the full width of the panel.
//
// A caveat that makes the numbers read low: `ch` is the width of the digit zero, which runs
// wider than an average Cyrillic lowercase letter, so a line holds roughly a fifth more
// characters than the number suggests.
export const READING_MEASURES = [64, 76, 92, 108, 124, 0] as const

export const DEFAULT_READING_MEASURE = 92

export const NO_MEASURE = 0

// An unknown code (a stale localStorage value, a family dropped from the list) falls
// back to the role's default rather than leaving the token empty.
export function fontStack(options: FontOption[], code: string, fallback: string): string {
  const chosen = options.find((option) => option.code === code)
    ?? options.find((option) => option.code === fallback)
  return chosen?.stack ?? SANS_FALLBACK
}

// The diagram renderer needs a typeface name, not a stack: it puts it into its own rule inside the
// SVG and appends fallbacks itself. Hence the stack's first family instead of the whole stack.
export function fontFamilyName(options: FontOption[], code: string, fallback: string): string {
  return fontStack(options, code, fallback).split(',')[0].replace(/['"]/g, '').trim()
}
