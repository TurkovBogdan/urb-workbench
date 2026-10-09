/**
 * The settings field contract: how the backend (`core._settings`) describes a configurable field.
 *
 * Fields arrive as a union type discriminated by `kind`. The contract lives in `shared/`, not in
 * the settings module, because shell components render it (`components/settings/`), and it has
 * more than one reader: today it is the settings screen, and there used to be the "Integrations"
 * screen too — it described credentials with the same descriptors.
 */

export type FieldKind =
  | 'int'
  | 'float'
  | 'bool'
  | 'str'
  | 'date'
  | 'datetime'
  | 'choice'
  | 'multichoice'
  | 'list'

/** Visible while the form value of `key` equals `equals`; evaluated on the frontend, not backend. */
export interface VisibleWhen {
  key: string
  equals: unknown
}

interface FieldBase {
  key: string
  kind: FieldKind
  label: string
  description: string
  default: unknown
  /** Title of the block the field is grouped into on screen. Empty — the field stands alone. */
  group: string
  visible_when: VisibleWhen | null
}

export interface IntFieldDescriptor extends FieldBase {
  kind: 'int'
  min: number | null
  max: number | null
}

export interface FloatFieldDescriptor extends FieldBase {
  kind: 'float'
  min: number | null
  max: number | null
  step: number
  decimals: number
}

export interface BoolFieldDescriptor extends FieldBase {
  kind: 'bool'
}

export interface StrFieldDescriptor extends FieldBase {
  kind: 'str'
  min_length: number | null
  max_length: number | null
  pattern: string | null
  lines: number
  secret: boolean
  // Secret fields only: whether the token is set (the token itself is never sent out).
  is_set?: boolean
}

export interface DateFieldDescriptor extends FieldBase {
  kind: 'date'
  min: string | null
  max: string | null
}

export interface DateTimeFieldDescriptor extends FieldBase {
  kind: 'datetime'
  min: string | null
  max: string | null
}

export interface ChoiceOption {
  code: string
  label: string
}

export interface ChoiceFieldDescriptor extends FieldBase {
  kind: 'choice'
  options: ChoiceOption[]
}

export interface MultiChoiceFieldDescriptor extends FieldBase {
  kind: 'multichoice'
  options: ChoiceOption[]
  min_items: number
  max_items: number | null
}

// The item descriptor inside a ListField — a list item is a value type, not a separate
// setting: the backend strips the keys listed below in `ui_descriptor`.
type SettingOwnKeys = 'key' | 'label' | 'description' | 'default' | 'group' | 'visible_when'

export type ListItemDescriptor =
  | Omit<IntFieldDescriptor, SettingOwnKeys>
  | Omit<FloatFieldDescriptor, SettingOwnKeys>
  | Omit<StrFieldDescriptor, SettingOwnKeys>
  | Omit<DateFieldDescriptor, SettingOwnKeys>
  | Omit<DateTimeFieldDescriptor, SettingOwnKeys>
  | Omit<ChoiceFieldDescriptor, SettingOwnKeys>

export interface ListFieldDescriptor extends FieldBase {
  kind: 'list'
  min_items: number
  max_items: number | null
  item: ListItemDescriptor
}

export type FieldDescriptor =
  | IntFieldDescriptor
  | FloatFieldDescriptor
  | BoolFieldDescriptor
  | StrFieldDescriptor
  | DateFieldDescriptor
  | DateTimeFieldDescriptor
  | ChoiceFieldDescriptor
  | MultiChoiceFieldDescriptor
  | ListFieldDescriptor
