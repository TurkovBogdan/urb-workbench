// The field limits of a codex and its notes mirror the DB columns (`codex/constants.py`): the field
// itself stops overtyping instead of the backend refusing what was already typed.
export const CODEX_SEGMENT_MAX = 64
export const CODEX_TITLE_MAX = 128
export const CODEX_DESCRIPTION_MAX = 512
export const CODEX_BODY_MAX = 65536

/** The path segment rule of `codex/rules.py`: a-z, 0-9, '_' and '-' (the set of the app's shared
 *  validator — `shared/utils/validators.ts`), starting with a letter or digit. */
export const CODEX_SEGMENT_PATTERN = /^[a-z0-9][a-z0-9_-]*$/

/** The tree is at most four levels: codex / note / note / note (`codex/rules.py::DEPTH_MAX`). */
export const CODEX_DEPTH_MAX = 4

/** The bounds of the navigation width the person drags (`core_interface/registry.py`). */
export const CODEX_NAV_WIDTH_MIN = 200
export const CODEX_NAV_WIDTH_MAX = 640
