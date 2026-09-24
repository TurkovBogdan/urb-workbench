// Вид блока кода в теле документа. Компонент `CodeBlock` умеет четыре вида, но выбирают из трёх:
// `compact` (однострочная командная плашка) не выбор человека, а следствие содержимого — фенс в
// одну строку рисуется ею всегда.

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

// Неизвестное значение (устаревший ключ в кеше браузера, выпавший из набора вид) откатывается к
// умолчанию, а не оставляет блок без вида.
export function codeVariant(code: string): CodeVariant {
  return CODE_VARIANTS.some((option) => option.code === code)
    ? (code as CodeVariant)
    : DEFAULT_CODE_VARIANT
}
