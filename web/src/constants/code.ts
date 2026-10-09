// Style of a code block in a document body. The `CodeBlock` component supports four styles, but the
// choice is among three: `compact` (a one-line command chip) is not the person's choice but a
// consequence of the content — a one-line fence is always rendered with it.

export type CodeVariant = 'icon' | 'accent' | 'minimal'

// Label and note come from the dictionary by code (`composables/useAppearanceOptions.ts`).
export interface CodeVariantOption {
  code: CodeVariant
}

export const CODE_VARIANTS: CodeVariantOption[] = [
  { code: 'icon' },
  { code: 'accent' },
  { code: 'minimal' },
]

export const DEFAULT_CODE_VARIANT: CodeVariant = 'minimal'

// An unknown value (a stale key in the browser cache, a style dropped from the set) falls back to
// the default rather than leaving the block without a style.
export function codeVariant(code: string): CodeVariant {
  return CODE_VARIANTS.some((option) => option.code === code)
    ? (code as CodeVariant)
    : DEFAULT_CODE_VARIANT
}
