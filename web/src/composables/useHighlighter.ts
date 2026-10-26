import {
  bundledLanguages,
  bundledLanguagesInfo,
  createHighlighter,
  type BundledLanguage,
  type Highlighter,
  type ThemedToken,
} from 'shiki'

// One highlighter for the app — the viewer's `CodeBlock` and the editor's code block share it, so a
// fence reads in the same colours being read and being edited. Languages are loaded on demand
// instead of up front, and a fence language is resolved against shiki's own bundle — it already
// knows the aliases (`js`, `sh`, `yml`, `py`), so a local whitelist would only narrow what shiki
// supports.
//
// Both schemes are highlighted at once. With `defaultColor: false` shiki writes no colour of its
// own: every token carries `--shiki-light` and `--shiki-dark`, and the CSS of the block decides
// which one is painted. That is what makes code follow the app theme instantly — the alternative,
// re-highlighting on every switch, would rebuild every block on the page.
const THEMES = { light: 'github-light-default', dark: 'github-dark-default' } as const
const PLAIN_TEXT = 'text'

// Names people write in a fence that shiki files under another id.
const ALIASES: Record<string, string> = { env: 'dotenv' }

const TOKEN_CACHE_LIMIT = 300

let highlighter: Highlighter | null = null
let creating: Promise<Highlighter> | null = null
const loadingLanguages = new Map<string, Promise<void>>()
const readyListeners = new Set<() => void>()
const tokenCache = new Map<string, CodeToken[]>()

function notifyReady(): void {
  for (const listener of readyListeners) listener()
}

async function getHighlighter(): Promise<Highlighter> {
  if (highlighter) return highlighter
  if (!creating) {
    creating = createHighlighter({ themes: Object.values(THEMES), langs: [] }).then((created) => {
      highlighter = created
      notifyReady()
      return created
    })
  }
  return creating
}

// An unknown language degrades to plain text: shiki has no auto-detection, and an unregistered
// id throws instead of rendering.
export function resolveLanguage(lang: string): string {
  const normalized = lang.trim().toLowerCase()
  const id = ALIASES[normalized] ?? normalized
  return id in bundledLanguages ? id : PLAIN_TEXT
}

function loadLanguageOnce(instance: Highlighter, language: string): Promise<void> {
  if (language === PLAIN_TEXT || instance.getLoadedLanguages().includes(language)) return Promise.resolve()
  const pending = loadingLanguages.get(language)
    ?? instance.loadLanguage(language as BundledLanguage).then(notifyReady)
  loadingLanguages.set(language, pending)
  return pending
}

export function useHighlighter() {
  async function highlight(code: string, lang: string): Promise<string> {
    const instance = await getHighlighter()
    const language = resolveLanguage(lang)
    await loadLanguageOnce(instance, language)
    return instance.codeToHtml(code, { lang: language, themes: THEMES, defaultColor: false })
  }

  return { highlight }
}

// ── The synchronous path ─────────────────────────────────────────────────────
// An editor colours text inside a transaction and cannot await there: tokens either exist right
// now, or the block stays plain and is repainted when `onLanguageReady` fires.

export interface CodeToken {
  /** Offset in the block's text. */
  offset: number
  length: number
  /** Both palettes as custom properties, ready for a `style` attribute. */
  style: string
}

/** Called whenever the highlighter or a language becomes available. Returns the unsubscribe. */
export function onLanguageReady(listener: () => void): () => void {
  readyListeners.add(listener)
  return () => readyListeners.delete(listener)
}

function styleOf(token: ThemedToken): string {
  return Object.entries(token.htmlStyle ?? {})
    .map(([property, value]) => `${property}:${value}`)
    .join(';')
}

/**
 * Tokens of one block, whitespace dropped. `null` — not ready yet (the highlighter or the language
 * is still loading, and the load is started here); the caller paints nothing and waits for
 * `onLanguageReady`.
 */
export function tokensFor(code: string, lang: string): CodeToken[] | null {
  const language = resolveLanguage(lang)
  if (language === PLAIN_TEXT) return []
  if (!highlighter) {
    void getHighlighter()
    return null
  }
  if (!highlighter.getLoadedLanguages().includes(language)) {
    void loadLanguageOnce(highlighter, language)
    return null
  }

  const key = `${language}\u0000${code}`
  const cached = tokenCache.get(key)
  if (cached) {
    // Re-insert so the entry counts as recently used.
    tokenCache.delete(key)
    tokenCache.set(key, cached)
    return cached
  }

  const { tokens } = highlighter.codeToTokens(code, {
    lang: language as BundledLanguage,
    themes: THEMES,
    defaultColor: false,
  })
  const result: CodeToken[] = []
  for (const line of tokens) {
    for (const token of line) {
      if (!token.content.trim()) continue
      result.push({ offset: token.offset, length: token.content.length, style: styleOf(token) })
    }
  }
  tokenCache.set(key, result)
  if (tokenCache.size > TOKEN_CACHE_LIMIT) tokenCache.delete(tokenCache.keys().next().value as string)
  return result
}

// ── The language list ────────────────────────────────────────────────────────

export interface LanguageOption {
  /** What goes into the fence and the header — shiki's id. */
  value: string
  /** The language's own name, shown beside the id in the list. */
  name: string
  /** Id, name and aliases in one string — what the search field matches. */
  search: string
}

// Every language shiki ships, not a hand-picked few: the list is searched, so its length costs
// nothing, and a block in a rare language is still one pick away. Only metadata is imported here —
// a grammar loads when a block first needs it.
export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { value: PLAIN_TEXT, name: 'Plain text', search: 'text plain txt' },
  ...bundledLanguagesInfo
    .map((info) => {
      const aliases = [...(info.aliases ?? []), ...Object.keys(ALIASES).filter((alias) => ALIASES[alias] === info.id)]
      // The name is glued into one word: a whole-word hit then means the id or an alias, so `ts`
      // ranks `typescript` (alias) above `glimmer-ts` (whose name, «Glimmer TS», has the word too).
      const name = info.name.replace(/\s+/g, '')
      return { value: info.id, name: info.name, search: [info.id, name, ...aliases].join(' ') }
    })
    .sort((a, b) => a.value.localeCompare(b.value)),
]
