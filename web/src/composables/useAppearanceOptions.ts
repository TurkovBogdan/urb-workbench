// Appearance choices with their labels and notes in the active language — one source for both
// places that offer them: the interface settings page and the document's own appearance column.
//
// The constants keep codes and proper nouns (family and palette names); everything that is a
// description comes from `settings.interface.option.<kind>.<code>`. The lists are computed, so an
// open select re-labels itself the moment the language changes.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { CODE_VARIANTS } from '@/constants/code'
import { DIAGRAM_ALIGNS, DIAGRAM_THEMES } from '@/constants/diagrams'
import {
  DIAGRAM_FONTS,
  HEADING_FONTS,
  INTERFACE_FONTS,
  MONO_FONTS,
  READING_FONTS,
  type FontOption,
} from '@/constants/fonts'
import { THEME_OPTIONS } from '@/constants/theme'

export type Described<T> = T & { label: string; note: string }

type OptionKind = 'theme' | 'code_variant' | 'diagram_align' | 'diagram_theme' | 'font'

export function useAppearanceOptions() {
  const { t } = useI18n()

  function describe<T extends { code: string; label?: string }>(kind: OptionKind, options: T[]) {
    return computed<Described<T>[]>(() =>
      options.map((option) => ({
        ...option,
        label: option.label ?? t(`settings.interface.option.${kind}.${option.code}.label`),
        note: t(`settings.interface.option.${kind}.${option.code}.note`),
      })),
    )
  }

  return {
    themes: describe('theme', THEME_OPTIONS),
    codeVariants: describe('code_variant', CODE_VARIANTS),
    diagramAligns: describe('diagram_align', DIAGRAM_ALIGNS),
    diagramThemes: describe('diagram_theme', DIAGRAM_THEMES),
    interfaceFonts: describe('font', INTERFACE_FONTS),
    readingFonts: describe('font', READING_FONTS),
    headingFonts: describe('font', HEADING_FONTS),
    monoFonts: describe('font', MONO_FONTS),
    diagramFonts: describe('font', DIAGRAM_FONTS),
  }
}

export type DescribedFont = Described<FontOption>
