import { defineStore } from 'pinia'
import { reactive, watch } from 'vue'
import { setLocale } from '@/plugins/i18n'
import { DEFAULT_LANGUAGE, appLocale, type AppLocale } from '@/constants/language'
import { boolCodec, intCodec, persisted, strCodec, type Codec } from '@/shared/utils/persisted'
import { synced } from '@/shared/utils/synced'
import {
  DEFAULT_CODE_SIZE,
  DEFAULT_DIAGRAM_FONT,
  DEFAULT_HEADING_FONT,
  DEFAULT_HEADING_WEIGHT,
  DEFAULT_INTERFACE_FONT,
  DEFAULT_MONO_FONT,
  DEFAULT_READING_FONT,
  DEFAULT_READING_MEASURE,
  DEFAULT_READING_SIZE,
  DEFAULT_READING_WEIGHT,
  HEADING_FONTS,
  INTERFACE_FONTS,
  MONO_FONTS,
  NO_MEASURE,
  READING_FONTS,
  fontStack,
} from '@/constants/fonts'
import {
  DEFAULT_CODE_VARIANT,
  codeVariant,
  type CodeVariant,
} from '@/constants/code'
import {
  DEFAULT_DIAGRAM_ALIGN,
  DEFAULT_DIAGRAM_HEIGHT,
  DEFAULT_DIAGRAM_THEME,
  diagramTheme,
  type DiagramAlign,
} from '@/constants/diagrams'
import {
  DEFAULT_THEME,
  onSystemSchemeChange,
  resolveScheme,
  type ColorScheme,
  type ThemeMode,
} from '@/constants/theme'
import vuetify from '@/plugins/vuetify'

// Central store for the user's local (client-side) settings — the single home for
// everything that used to live scattered across plugins/preferences.ts, layout/store.ts
// and plugins/i18n.ts. State holds NORMAL typed values (real booleans / enums); the
// codec translates each to/from its localStorage string (see shared/utils/persisted).
//
// This holds the person's CHOICES — what they once set up for themselves. Interface state
// (which order they left in which list while working) is the neighbouring store `ui-state`.
//
// The app's appearance is driven by `synced`: the source of truth is the database (the
// `core_interface` module), and localStorage underneath stays a cache that paints the page before
// the first frame. Key names match the registry keys on the backend. What the registry doesn't
// have — timezone, date format and the showcase legacy — stays on `persisted`, i.e. lives only in
// this browser.

export const AUTO = 'auto'

// Selectable date formats as Luxon tokens. "auto" is handled separately (locale-derived).
export const DATE_FORMATS = ['dd.MM.yyyy', 'dd/MM/yyyy', 'yyyy-MM-dd', 'MM/dd/yyyy'] as const

export const useSettingsStore = defineStore('settings', () => {
  // `reactive` unwraps the nested refs/computed, so `settings.locale.timezone` reads the
  // plain value and `settings.message.unsafe` reads a real boolean — while each underlying
  // ref keeps its own persistence watcher.
  const locale = reactive({
    // Repaired on read: an unknown code would reach vue-i18n and every string would render as
    // its key path.
    language: synced<AppLocale>('interface_language', DEFAULT_LANGUAGE, {
      parse: appLocale,
      serialize: (v) => v,
    }),
    timezone: persisted('app.timezone', AUTO, strCodec),
    dateFormat: persisted('app.date_format', AUTO, strCodec),
  })

  // `immediate` applies the cached choice while the store is created in main.ts — before the
  // first paint; the value hydrated from the backend later arrives through the same watcher.
  watch(() => locale.language, (language) => setLocale(language), { immediate: true })

  const ui = reactive({
    sidebarCollapsed: synced('interface_sidebar_collapsed', false, boolCodec),
  })

  const message = reactive({
    mode: persisted('app.message.mode', 'text', strCodec), // 'html' | 'text'
    unsafe: persisted('app.message.unsafe', false, boolCodec), // true = safe view disabled (remote content shown)
  })

  const appearance = reactive({
    theme: synced<ThemeMode>('interface_theme', DEFAULT_THEME, strCodec as Codec<ThemeMode>),
  })

  // While the mode is `system` the OS can flip underneath us, so the scheme is re-applied on
  // the media-query event as well as on the choice itself.
  watch(() => appearance.theme, (mode) => applyScheme(resolveScheme(mode)), { immediate: true })
  onSystemSchemeChange((scheme) => {
    if (appearance.theme === 'system') applyScheme(scheme)
  })

  const typography = reactive({
    interfaceFont: synced('interface_font', DEFAULT_INTERFACE_FONT, strCodec),
    readingFont: synced('interface_font_reading', DEFAULT_READING_FONT, strCodec),
    headingFont: synced('interface_font_heading', DEFAULT_HEADING_FONT, strCodec),
    readingSize: synced('interface_font_reading_size', DEFAULT_READING_SIZE, intCodec),
    readingWeight: synced('interface_font_reading_weight', DEFAULT_READING_WEIGHT, intCodec),
    headingWeight: synced('interface_font_heading_weight', DEFAULT_HEADING_WEIGHT, intCodec),
    readingMeasure: synced('interface_font_reading_measure', DEFAULT_READING_MEASURE, intCodec),
    monoFont: synced('interface_font_mono', DEFAULT_MONO_FONT, strCodec),
    // The block style is repaired on read: otherwise a corrupted key would spread to every block.
    codeVariant: synced<CodeVariant>('interface_code_variant', DEFAULT_CODE_VARIANT, {
      parse: codeVariant,
      serialize: (v) => v,
    }),
    codeSize: synced('interface_font_code_size', DEFAULT_CODE_SIZE, intCodec),
    // Line numbers in a code block: the choice sets what the block opens with. The button in the
    // block's own header stays — it toggles numbers in one listing without touching the setting.
    codeLineNumbers: synced('interface_code_line_numbers', true, boolCodec),
  })

  // Diagram styling is its own node, not part of typography: it isn't distributed via tokens, the
  // diagram component reads it itself. The typeface is here too, so diagram settings have one
  // home; it doesn't go to CSS — the renderer puts the family name inside the SVG and measures
  // label widths by it.
  const diagrams = reactive({
    theme: synced('interface_diagram_theme', DEFAULT_DIAGRAM_THEME, {
      parse: diagramTheme,
      serialize: (v) => v,
    }),
    font: synced('interface_font_diagram', DEFAULT_DIAGRAM_FONT, strCodec),
    align: synced('interface_diagram_align', DEFAULT_DIAGRAM_ALIGN, strCodec as Codec<DiagramAlign>),
    maxHeight: synced('interface_diagram_max_height', DEFAULT_DIAGRAM_HEIGHT, intCodec),
  })

  watch(
    () => [
      typography.interfaceFont,
      typography.readingFont,
      typography.headingFont,
      typography.readingSize,
      typography.readingWeight,
      typography.headingWeight,
      typography.readingMeasure,
      typography.monoFont,
      typography.codeSize,
    ],
    () => applyTypographyTokens(typography),
    { immediate: true },
  )

  return { locale, ui, message, appearance, typography, diagrams }
})

// Two consumers, one name: the attribute drives the CSS token palettes (styles/main.scss),
// which is what the app itself is painted from, and Vuetify is told separately because it
// colours its own components from its theme map rather than from the tokens.
function applyScheme(scheme: ColorScheme): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = scheme
  vuetify.theme.change(scheme)
}

// The choices reach CSS as tokens on <html>, which outrank the `:root` defaults in main.scss.
// Vuetify's own `--v-font-*` are set alongside `--font`: its typography roles read those, and
// left unset they keep rendering the framework default (Roboto) wherever a component style
// wins the cascade.
interface TypographyChoice {
  interfaceFont: string
  readingFont: string
  headingFont: string
  readingSize: number
  readingWeight: number
  headingWeight: number
  readingMeasure: number
  monoFont: string
  codeSize: number
}

function applyTypographyTokens({ interfaceFont, readingFont, headingFont, readingSize, readingWeight, headingWeight, readingMeasure, monoFont, codeSize }: TypographyChoice): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement.style
  const ui = fontStack(INTERFACE_FONTS, interfaceFont, DEFAULT_INTERFACE_FONT)
  root.setProperty('--font', ui)
  root.setProperty('--v-font-body', ui)
  root.setProperty('--v-font-heading', ui)
  root.setProperty('--font-reading', fontStack(READING_FONTS, readingFont, DEFAULT_READING_FONT))
  // The "same as text" option carries a reference to the neighbouring token as its stack, so there
  // is no branch here: with it `--font-heading` gets `var(--font-reading)` and follows it by itself.
  root.setProperty('--font-heading', fontStack(HEADING_FONTS, headingFont, DEFAULT_HEADING_FONT))
  root.setProperty('--font-mono', fontStack(MONO_FONTS, monoFont, DEFAULT_MONO_FONT))
  // A stale or hand-edited storage value would otherwise reach CSS as `NaNpx` / `NaNch` and
  // take the whole prose scale — or the column width — down with it.
  const size = Number.isFinite(readingSize) ? readingSize : DEFAULT_READING_SIZE
  root.setProperty('--reading-size', `${size}px`)
  const weight = Number.isFinite(readingWeight) ? readingWeight : DEFAULT_READING_WEIGHT
  root.setProperty('--reading-weight', `${weight}`)
  const heading = Number.isFinite(headingWeight) ? headingWeight : DEFAULT_HEADING_WEIGHT
  root.setProperty('--heading-weight', `${heading}`)
  const measure = Number.isFinite(readingMeasure) ? readingMeasure : DEFAULT_READING_MEASURE
  root.setProperty('--reading-measure', measure === NO_MEASURE ? 'none' : `${measure}ch`)
  // The listing font size belongs to the reading zone, not to every code block in the app:
  // design-system snippets and hint panels live their own life. The reading zone passes it on
  // itself (`MarkdownRenderer` → `--code-size`), hence the role prefix in the token name.
  const code = Number.isFinite(codeSize) ? codeSize : DEFAULT_CODE_SIZE
  root.setProperty('--reading-code-size', `${code}px`)
}

// IANA zone list for the picker; empty if the engine lacks Intl.supportedValuesOf.
export function timezoneOptions(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
  try {
    return intl.supportedValuesOf ? intl.supportedValuesOf('timeZone') : []
  } catch {
    return []
  }
}
