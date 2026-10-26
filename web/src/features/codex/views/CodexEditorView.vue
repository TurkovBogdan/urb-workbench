<script setup lang="ts">
// The codex materials — `/codex/materials/CODEX@…`, one address for a codex and a note (they share
// the prefix); without a code it opens the first codex of the canvas. It is also the page
// `interface_open(CODEX@…)` opens for the agent.
//
// TEST IMPLEMENTATION (TASK@8EAB179834): the first working cut; the look and the words are still to
// be settled, and a clash with a concurrent edit is resolved by "last save wins" for now.
//
// On the right — the canvas of the CURRENT workspace: every codex mounted into it and its notes,
// exactly what the agent reads. On the left — the selected node: a codex shows its rules, a note
// its text. A codex is shared, so an edit lands in every workspace it is mounted into; the header
// says how many. A code whose codex is not mounted here gets that said, with the way to the list.
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  provide,
  reactive,
  ref,
  watch,
  type ComponentPublicInstance,
} from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import AppDialog from '@/components/AppDialog.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import CopyCodeButton from '@/components/CopyCodeButton.vue'
import { FILE_BINDING_EDITOR } from '@/components/files/fileBinding'
import InvisibleField from '@/components/InvisibleField.vue'
import SectionError from '@/components/SectionError.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import SearchField, { type SearchScope } from '@/components/SearchField.vue'
import VSelectSearch from '@/components/VSelectSearch.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { MarkdownEditor } from '@/components/markdown/editor'
import { ApiError } from '@/api/client/internal'
import { errorText } from '@/api/errorText'
import { pushToast } from '@/composables/useToasts'
import { useChangeSubscription } from '@/composables/useChangeSubscription'
import { useFindShortcut } from '@/composables/useFindShortcut'
import { useClipboard } from '@/composables/useClipboard'
import { IconCheck, IconCopy, IconFileText, IconSettings } from '@tabler/icons-vue'
import type { Change } from '@/stores/changes'
import { providePreviewWorkspace } from '@/stores/preview'
import { useSettingsStore } from '@/stores/settings'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'
import { persisted, strCodec } from '@/shared/utils/persisted'
import { keepSegmentChars } from '@/shared/utils/validators'

import CodexNoteFiles from '../components/CodexNoteFiles.vue'
import CodexTree from '../components/CodexTree.vue'
import {
  canvasTree,
  createNote,
  deleteNote,
  getCodex,
  getNote,
  moveNote,
  restoreNote,
  searchCanvas,
  updateCodex,
  updateNote,
  type CodexDetail,
  type CodexNote,
  type TreeNode,
} from '../api'
import {
  CODEX_BODY_MAX,
  CODEX_DEPTH_MAX,
  CODEX_DESCRIPTION_MAX,
  CODEX_NAV_WIDTH_MAX,
  CODEX_NAV_WIDTH_MIN,
  CODEX_SEGMENT_MAX,
  CODEX_SEGMENT_PATTERN,
  CODEX_TITLE_MAX,
} from '../labels'
import { CODEX_DOCUMENT_FEATURES } from '../editor'
import { noteFileAttach, noteFileEditor, noteFileRefuse } from '../fileAttach'
import type { NoteDrop } from '../drag'
import { CODEX_AVAILABLE, codexNodePath, displayPath } from '../paths'

const TYPING_PAUSE = 700
const ROUTE_NAME = 'codex-editor'
const NAV_WIDTH_KEY_STEP = 16

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const context = useWorkspaceContextStore()
const settings = useSettingsStore()
const { copy: copyText, isCopied } = useClipboard()

// ── Navigation width ──────────────────────────────────────────────────────────
// The person drags the navigation's edge; the width follows the pointer on screen and reaches the
// interface settings once, on release — not with every pixel of the drag.
const resizing = ref(false)

function clampNavWidth(width: number): number {
  if (!Number.isFinite(width)) return CODEX_NAV_WIDTH_MIN
  return Math.round(Math.min(CODEX_NAV_WIDTH_MAX, Math.max(CODEX_NAV_WIDTH_MIN, width)))
}

const navWidth = ref(clampNavWidth(settings.ui.codexNavWidth))
watch(() => settings.ui.codexNavWidth, (width) => { if (!resizing.value) navWidth.value = clampNavWidth(width) })

function startResize(event: PointerEvent) {
  if (event.button !== 0) return
  event.preventDefault()
  const handle = event.currentTarget as HTMLElement
  const startX = event.clientX
  // From the width on screen, not the stored one: on a narrow window the grid gives the stored
  // width up, and counting from it the first stretch of a drag would move nothing.
  const startWidth = clampNavWidth(handle.parentElement?.getBoundingClientRect().width ?? navWidth.value)
  handle.setPointerCapture(event.pointerId)
  resizing.value = true
  const follow = (move: PointerEvent) => { navWidth.value = clampNavWidth(startWidth + move.clientX - startX) }
  const release = () => {
    handle.removeEventListener('pointermove', follow)
    handle.removeEventListener('pointerup', release)
    handle.removeEventListener('pointercancel', release)
    resizing.value = false
    settings.ui.codexNavWidth = navWidth.value
  }
  handle.addEventListener('pointermove', follow)
  handle.addEventListener('pointerup', release)
  handle.addEventListener('pointercancel', release)
}

function resizeByKey(direction: number) {
  navWidth.value = clampNavWidth(navWidth.value + direction * NAV_WIDTH_KEY_STEP)
  settings.ui.codexNavWidth = navWidth.value
}

const code = computed(() => String(route.params.code ?? '').toUpperCase())
const workspace = computed(() => context.currentWorkspace?.code ?? '')

const tree = ref<TreeNode[]>([])
const codex = ref<CodexDetail | null>(null)
const note = ref<CodexNote | null>(null)
// A file pasted or dropped into a live note's text is the note's; the codex itself holds none. One
// function per note code, not per read of the note: the editor tells a holder change by a new
// function, and cancels an insertion still uploading (`behavior/fileAttach.ts`).
const attachHolder = computed(() => (note.value && !note.value.deleted_at ? note.value.code : null))
const attachToNote = computed(() => (attachHolder.value ? noteFileAttach(attachHolder.value) : undefined))
const loading = ref(false)
const error = ref<unknown>(null)
const saveError = ref<string | null>(null)

// The codes of a note are read in the current workspace, as everywhere on this page, and its files
// are named as the note names them in its files panel.
providePreviewWorkspace(workspace, () => (note.value?.code === code.value ? code.value : undefined))
// A picture of the note shown full screen: its title and description are the note's to edit.
provide(
  FILE_BINDING_EDITOR,
  noteFileEditor(() => (note.value?.code === code.value ? code.value : null), () => Boolean(note.value?.deleted_at)),
)

/** Every node of the canvas by code, with its parent's code and its codex's. */
const index = computed(() => {
  const map = new Map<string, { node: TreeNode; parent: string | null; codex: string; depth: number }>()
  const walk = (nodes: TreeNode[], parent: string | null, codexCode: string | null, depth: number) => {
    for (const node of nodes) {
      const owner = codexCode ?? node.code
      map.set(node.code, { node, parent, codex: owner, depth })
      walk(node.children, node.code, owner, depth + 1)
    }
  }
  walk(tree.value, null, null, 1)
  return map
})

const inCanvas = computed(() => index.value.has(code.value))
const isCodex = computed(() => index.value.get(code.value)?.depth === 1)
/** The open record's virtual path in the canvas, as the tree holds it — a rename shows after save. */
const openPath = computed(() => displayPath(index.value.get(code.value)?.node.path ?? ''))

// The open record is kept in view in the tree: arriving by a link, `interface_open`, a new note or
// a move would otherwise leave it scrolled far out of the navigation. Only the tree's own scroller
// moves, and only when the row is out of sight — a click on a visible row must not jolt the list.
function revealSelectedRow(): void {
  const scroller = (navCard.value?.$el as HTMLElement | undefined)?.querySelector<HTMLElement>('.codex-editor__tree')
  const row = scroller?.querySelector<HTMLElement>('.codex-tree__row--selected')
  if (!scroller || !row) return
  const box = scroller.getBoundingClientRect()
  const at = row.getBoundingClientRect()
  if (at.top >= box.top && at.bottom <= box.bottom) return
  scroller.scrollTop += at.top - box.top - (box.height - at.height) / 2
}

watch([code, tree], () => { void nextTick(revealSelectedRow) }, { flush: 'post' })

// ── Loading ───────────────────────────────────────────────────────────────────
let active = false

async function loadTree(): Promise<void> {
  await context.ensure()
  const rows = workspace.value
    ? await canvasTree(workspace.value, settings.ui.codexShowDeleted, { report: false })
    : []
  tree.value = rows
  // The sidebar entry opens the materials without a code: land on the first codex of the canvas.
  if (!code.value && rows.length && route.name === ROUTE_NAME) {
    await router.replace(codexNodePath(rows[0]!.code))
    return
  }
  // The address may name a node the tree did not hold a moment ago — a note just created and
  // navigated to: it is read as soon as the tree has it.
  if (inCanvas.value && (codex.value ?? note.value)?.code !== code.value) await loadNode()
}

// ── Deleted notes ─────────────────────────────────────────────────────────────
// Shown on request (the gear in the navigation, kept in the interface settings) right in the tree,
// in their places: a deleted note is restored where it stood, and a branch deleted whole stands
// under its root. How a codex is mounted here is managing, not reading — it lives among the
// available codexes.
watch(() => settings.ui.codexShowDeleted, () => { if (active) void loadTree() })

async function restore(node: TreeNode) {
  await act(() => restoreNote(node.code))
}

// ── Tree filter ───────────────────────────────────────────────────────────────
// Narrows the tree to what matches by title or segment, keeping the way down to each match.
const filter = ref('')
const navCard = ref<ComponentPublicInstance | null>(null)
useFindShortcut(navCard)

// The search field's depth, as on the task list: title and segment are the base and always
// searched — they name a record in the tree; the contents (description and text) are a layer switched on by
// the button inside the field. The tree carries no texts, so that layer asks the backend — the
// same search the agent's `codex_search` runs — and its answer joins the base as a set of codes.
const SCOPE_CONTENT = 'content'
// For a single letter the backend would read every text of the canvas for a junk answer — the same
// threshold as the task list's deep search.
const MIN_CONTENT_QUERY_LENGTH = 2
const CONTENT_SEARCH_PAUSE = 250

const searchScopes = computed<SearchScope[]>(() => [
  { key: SCOPE_CONTENT, icon: IconFileText, label: t('codex.editor.search_content') },
])
const activeScopes = ref<string[]>([])
const contentCodes = ref<Set<string> | null>(null)

let contentRun = 0
let contentTimer: ReturnType<typeof setTimeout> | null = null

async function runContentSearch(): Promise<void> {
  const run = ++contentRun
  const needle = filter.value.trim()
  if (!activeScopes.value.includes(SCOPE_CONTENT) || needle.length < MIN_CONTENT_QUERY_LENGTH || !workspace.value) {
    contentCodes.value = null
    return
  }
  try {
    const codes = await searchCanvas(workspace.value, needle, { report: false })
    if (run === contentRun) contentCodes.value = new Set(codes)
  } catch {
    if (run === contentRun) contentCodes.value = null
  }
}

watch([filter, activeScopes, workspace], () => {
  if (contentTimer) clearTimeout(contentTimer)
  contentTimer = setTimeout(() => { contentTimer = null; void runContentSearch() }, CONTENT_SEARCH_PAUSE)
})

onBeforeUnmount(() => { if (contentTimer) clearTimeout(contentTimer) })

function narrowed(nodes: TreeNode[], needle: string): TreeNode[] {
  return nodes.flatMap((node) => {
    const children = narrowed(node.children, needle)
    const hit =
      node.title.toLocaleLowerCase().includes(needle) ||
      node.segment.includes(needle) ||
      !!contentCodes.value?.has(node.code)
    return hit || children.length ? [{ ...node, children: hit ? node.children : children }] : []
  })
}

const shownTree = computed(() => {
  const needle = filter.value.trim().toLocaleLowerCase()
  return needle ? narrowed(tree.value, needle) : tree.value
})

// ── Folding ───────────────────────────────────────────────────────────────────
// Which rows are folded, kept in the browser across visits — the navigation is the person's
// arrangement of their materials. Everything is open by default; a search unfolds what it found,
// and opening a node unfolds the way down to it.
const collapsedCodes = persisted('ui.codex.tree.collapsed', '', strCodec)
const collapsed = computed(() => new Set(collapsedCodes.value.split(',').filter(Boolean)))
const shownCollapsed = computed(() => (filter.value.trim() ? new Set<string>() : collapsed.value))

function setCollapsed(next: Set<string>) {
  collapsedCodes.value = [...next].join(',')
}

function toggle(node: TreeNode) {
  const next = new Set(collapsed.value)
  if (next.has(node.code)) next.delete(node.code)
  else next.add(node.code)
  setCollapsed(next)
}

// The way down is unfolded once per arrival at a node — not on every re-read of the tree, or a
// branch the person folded around the open node would spring open again on the next change.
let reveal: string | null = null

function revealOpenNode() {
  if (!reveal || !index.value.has(reveal)) return
  const next = new Set(collapsed.value)
  let parent = index.value.get(reveal)?.parent ?? null
  let changed = false
  while (parent) {
    changed = next.delete(parent) || changed
    parent = index.value.get(parent)?.parent ?? null
  }
  reveal = null
  if (changed) setCollapsed(next)
}

watch(code, (value) => { reveal = value; revealOpenNode() }, { immediate: true })
watch(index, revealOpenNode)

// A re-read of the node on screen keeps it on screen until the fresh one arrives: emptied, the
// editor would unmount, and a file still uploading into the note's text would lose its place
// without a word. Another node starts empty, as before.
async function loadNode(): Promise<void> {
  if ((codex.value ?? note.value)?.code !== code.value || !inCanvas.value) {
    codex.value = null
    note.value = null
  }
  if (!inCanvas.value) return
  if (isCodex.value) {
    codex.value = await getCodex(code.value, { report: false })
    note.value = null
  } else {
    note.value = await getNote(code.value, { report: false })
    codex.value = null
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    codex.value = null
    note.value = null
    await loadTree()
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

onActivated(() => { active = true; void load() })
onDeactivated(() => { active = false })
watch(code, () => { if (active && route.name === ROUTE_NAME) void loadNode() })
watch(workspace, () => { if (active) void load() })

// ── Draft and saving ──────────────────────────────────────────────────────────
const draft = reactive({ title: '', segment: '', description: '', body: '' })

watch([codex, note], () => {
  const row = codex.value ?? note.value
  Object.assign(draft, {
    title: row?.title ?? '',
    segment: row?.segment ?? '',
    description: row?.description ?? '',
    body: row?.body ?? '',
  })
  saveError.value = null
})

let timer: ReturnType<typeof setTimeout> | null = null
let saving: Promise<unknown> = Promise.resolve()

function dirty(): boolean {
  const row = codex.value ?? note.value
  if (!row) return false
  return (['title', 'segment', 'description', 'body'] as const).some((field) => draft[field] !== row[field])
}

/**
 * The sibling already holding the draft's segment, if any — checked here, before the request, so
 * the refusal stands under the segment field in the person's language rather than as the backend's
 * text under the page. Live siblings only: a deleted one frees its segment. A codex's segment is
 * checked by the backend (codexes are not all in the canvas).
 */
const segmentHolder = computed(() => {
  if (!note.value) return null
  const own = index.value.get(code.value)
  const parent = own?.parent ? index.value.get(own.parent)?.node : null
  return parent?.children.find((child) => !child.deleted && child.code !== code.value && child.segment === draft.segment) ?? null
})

async function commit(): Promise<void> {
  if (timer) { clearTimeout(timer); timer = null }
  // Back to what is stored: nothing to save, and a refusal shown for an earlier value is stale.
  if (!dirty()) { saveError.value = null; return }
  if (!draft.title.trim() || !CODEX_SEGMENT_PATTERN.test(draft.segment) || segmentHolder.value) return
  const body = {
    title: draft.title.trim(),
    segment: draft.segment,
    description: draft.description,
    body: draft.body,
  }
  const target = code.value
  const request = codex.value ? updateCodex(target, body, { report: false }) : updateNote(target, body, { report: false })
  saving = request
  try {
    const saved = await request
    if (target !== code.value) return
    if (codex.value) codex.value = saved as CodexDetail
    else note.value = saved as CodexNote
    saveError.value = null
    // A new title or segment shows in the tree.
    await loadTree()
  } catch (e) {
    if (target === code.value) saveError.value = errorText(e)
  }
}

function schedule(): void {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { timer = null; void commit() }, TYPING_PAUSE)
}

// Only what a segment may hold gets in; the raw value first and the filtered one a tick later, or a
// refused character would stay on screen when filtering returns the old value.
async function onSegmentInput(value: string) {
  draft.segment = value
  await nextTick()
  draft.segment = keepSegmentChars(value)
  schedule()
}

onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
onBeforeRouteLeave(() => { void commit() })

// ── Live updates ──────────────────────────────────────────────────────────────
// The agent writes notes through MCP: the tree follows every change of the canvas; the open node
// is re-read only when the person has nothing unsaved in it.
async function reloadLive(changes: Change[] = []): Promise<void> {
  if (dragging.value) {
    reloadWaiting = true
    return
  }
  await saving
  await loadTree()
  const touches = changes.length === 0 || changes.some((change) => change.ids.includes(code.value))
  if (touches && !dirty()) await loadNode()
}

useChangeSubscription({
  entities: ['codex.codex', 'codex.note', 'codex.mount'],
  match: () => true,
  onChange: (changes) => { void reloadLive(changes) },
  onResync: () => { void reloadLive() },
  reloadsOnReturn: true,
})

// ── Tree actions ──────────────────────────────────────────────────────────────
function select(node: TreeNode) {
  void commit()
  void router.push(codexNodePath(node.code))
}

// "Add nested" makes the note at once, with no dialog: "New note" under the segment `new-001`, the
// first number free among the live siblings, then opens it with the cursor in the title — naming
// it is the next thing the person does anyway. A segment taken a moment ago by someone else (the
// agent writes too) is refused by the backend; the next number is tried then.
const NEW_SEGMENT_ATTEMPTS = 5
/** The note just made, whose title takes the focus as soon as its page is read. */
let focusTitleOf: string | null = null

function newSegment(taken: Set<string>): string {
  for (let n = 1; ; n += 1) {
    const segment = `new-${String(n).padStart(3, '0')}`
    if (!taken.has(segment)) return segment
  }
}

async function add(node: TreeNode) {
  void commit()
  const taken = new Set(node.children.filter((child) => !child.deleted).map((child) => child.segment))
  for (let attempt = 0; attempt < NEW_SEGMENT_ATTEMPTS; attempt += 1) {
    const segment = newSegment(taken)
    try {
      const row = await createNote(
        { parent_code: node.code, segment, title: t('codex.form.note_title'), description: '', body: '' },
        { report: false },
      )
      if (collapsed.value.has(node.code)) {
        const next = new Set(collapsed.value)
        next.delete(node.code)
        setCollapsed(next)
      }
      focusTitleOf = row.code
      await loadTree()
      await router.push(codexNodePath(row.code))
      return
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 409)) {
        pushToast(errorText(e), 'error')
        return
      }
      taken.add(segment)
    }
  }
  pushToast(t('codex.editor.new_note_failed'), 'error')
}

watch(note, async (row) => {
  if (!row || row.code !== focusTitleOf) return
  focusTitleOf = null
  await nextTick()
  const input = document.querySelector<HTMLInputElement>('.codex-editor__title input')
  input?.focus()
  input?.select()
})

async function act(run: () => Promise<unknown>) {
  try {
    await run()
    await loadTree()
    // A move changes the open node's path; nothing unsaved — re-read it.
    if (!dirty()) await loadNode()
  } catch (e) {
    pushToast(errorText(e), 'error')
  }
}

/** The node's real siblings — from the full tree, not the filtered one on screen. */
function siblingsOf(node: TreeNode): TreeNode[] {
  const parent = index.value.get(node.code)?.parent
  return parent ? index.value.get(parent)?.node.children ?? [] : tree.value
}

/** The live siblings only — the row the backend places a note in; deleted ones are not in it. */
function liveSiblingsOf(node: TreeNode): TreeNode[] {
  return siblingsOf(node).filter((sibling) => !sibling.deleted)
}

function up(node: TreeNode) {
  const siblings = liveSiblingsOf(node)
  const at = siblings.findIndex((s) => s.code === node.code)
  if (at <= 0) return
  const after = at >= 2 ? siblings[at - 2]!.code : null
  void act(() => moveNote(node.code, { after_code: after }))
}

function down(node: TreeNode) {
  const siblings = liveSiblingsOf(node)
  const at = siblings.findIndex((s) => s.code === node.code)
  const next = siblings[at + 1]
  if (next) void act(() => moveNote(node.code, { after_code: next.code }))
}

// ── Where a note may go ───────────────────────────────────────────────────────
// The service's rules, asked before a move is offered — by dragging and by the menu alike: a note
// lands under a codex or a note of any mounted codex, never inside its own branch, never deeper
// than four levels with its branch counted whole, never next to a sibling holding its segment.
// Deleted notes on screen take no part: a deleted note neither moves nor takes one under it, and
// the service counts depth and segments over live notes only.
function heightOf(node: TreeNode): number {
  return 1 + Math.max(0, ...node.children.filter((child) => !child.deleted).map(heightOf))
}

function accepts(parent: string, code: string): boolean {
  const moving = index.value.get(code)
  const target = index.value.get(parent)
  if (!moving || !target || moving.depth === 1) return false
  if (moving.node.deleted || target.node.deleted) return false
  for (let at: string | null = parent; at; at = index.value.get(at)?.parent ?? null) {
    if (at === code) return false
  }
  if (target.depth + heightOf(moving.node) > CODEX_DEPTH_MAX) return false
  return !target.node.children.some(
    (child) => !child.deleted && child.code !== code && child.segment === moving.node.segment,
  )
}

// ── Dragging ──────────────────────────────────────────────────────────────────
// The tree moves the note at once, before the backend answers — waiting for it would put the row
// back under the hand for a moment. The answer is reconciled by re-reading the tree; a refusal is
// reported and the re-read puts everything back. A folded parent that took the note unfolds:
// otherwise the note just dropped would vanish from sight. While a note is held the live updates
// wait — swapping the tree under it would yank the drop target away.
const dragging = ref(false)
let reloadWaiting = false

function setDragging(on: boolean) {
  dragging.value = on
  document.body.classList.toggle('codex-dragging', on)
  if (!on && reloadWaiting) {
    reloadWaiting = false
    void reloadLive()
  }
}

onBeforeUnmount(() => document.body.classList.remove('codex-dragging'))

function applyDrop({ code, parent, after }: NoteDrop): void {
  const node = index.value.get(code)?.node
  const target = index.value.get(parent)?.node
  if (!node || !target) return
  const from = siblingsOf(node)
  from.splice(from.indexOf(node), 1)
  const at = after ? target.children.findIndex((child) => child.code === after) + 1 : 0
  target.children.splice(at, 0, node)
}

function drop(move: NoteDrop) {
  applyDrop(move)
  if (collapsed.value.has(move.parent)) {
    const next = new Set(collapsed.value)
    next.delete(move.parent)
    setCollapsed(next)
  }
  void act(() => moveNote(move.code, { parent_code: move.parent, after_code: move.after }))
}

// Move under another parent from the menu: any place the tree's rules allow, its current parent
// left out.
const moveOpen = ref(false)
const moving = ref<TreeNode | null>(null)
const moveTarget = ref<string | null>(null)

const moveTargets = computed(() => {
  const node = moving.value
  if (!node) return []
  const own = index.value.get(node.code)
  return [...index.value.values()]
    .filter((entry) => entry.node.code !== own?.parent && accepts(entry.node.code, node.code))
    .map((entry) => {
      const codex = index.value.get(entry.codex)?.node
      const path = displayPath(entry.node.path)
      return {
        value: entry.node.code,
        // The search row of the list filters by `title`, so it holds everything a target is
        // found by — its path, its name and its code; the row itself draws path and name apart.
        title: `${path} ${entry.node.title} ${entry.node.code}`,
        path,
        name: entry.node.title,
        icon: codex?.icon ?? '',
        color: codex?.color ?? '',
      }
    })
})

function move(node: TreeNode) {
  moving.value = node
  moveTarget.value = null
  moveOpen.value = true
}

async function confirmMove() {
  const node = moving.value
  const target = moveTarget.value
  moveOpen.value = false
  if (node && target) await act(() => moveNote(node.code, { parent_code: target }))
}

// Delete: always asked first. A note alone is asked about by its title; a note with live children
// says the whole branch goes with it and names them. Either can be restored, so the question is
// short. The tree's children may be a moment stale — the backend refusing a lone delete for
// children that appeared meanwhile turns the question into the branch one.
const removeOpen = ref(false)
const removing = ref<TreeNode | null>(null)
const removingChildren = ref<string[]>([])

function remove(node: TreeNode) {
  removing.value = node
  removingChildren.value = node.children.filter((child) => !child.deleted).map((child) => child.title)
  removeOpen.value = true
}

const removeDialog = computed(() =>
  removingChildren.value.length
    ? {
        title: t('codex.tree.branch_title'),
        text: t('codex.tree.branch_text', { children: removingChildren.value.join(', ') }),
        confirm: t('codex.tree.branch_confirm'),
      }
    : {
        title: t('codex.tree.delete_title'),
        text: t('codex.tree.delete_text', { title: removing.value?.title ?? '' }),
        confirm: t('codex.tree.delete'),
      },
)

async function confirmRemove() {
  const node = removing.value
  removeOpen.value = false
  if (!node) return
  try {
    await deleteNote(node.code, removingChildren.value.length > 0, { report: false })
    await afterRemove(node)
  } catch (e) {
    if (e instanceof ApiError && e.code === 'codex.note.has_children') {
      removingChildren.value = String(e.params?.children ?? '').split(',').map((s) => s.trim()).filter(Boolean)
      removeOpen.value = true
    } else {
      pushToast(errorText(e), 'error')
    }
  }
}

async function afterRemove(node: TreeNode) {
  const parent = index.value.get(node.code)?.parent
  await loadTree()
  if (code.value === node.code && parent) void router.replace(codexNodePath(parent))
}
</script>

<template>
  <PageLayout>
    <SectionError v-if="error" :error="error" />

    <div v-else-if="!loading && !tree.length" class="codex-editor__empty">
      <p>{{ t('codex.editor.nothing_mounted') }}</p>
      <VBtn variant="flat" color="primary" :to="CODEX_AVAILABLE">{{ t('codex.editor.to_list') }}</VBtn>
    </div>

    <div
      v-else
      class="codex-editor"
      :class="{ 'codex-editor--resizing': resizing }"
      :style="{ '--codex-nav-width': `${navWidth}px` }"
    >
      <!-- The file navigation: the mounted codexes as roots, their notes folding under them. -->
      <div class="codex-editor__side">
        <VCard ref="navCard" tag="nav" variant="outlined" rounded="lg" class="codex-editor__nav">
          <!-- Ctrl+F lands here (`useFindShortcut`): on this page "find" means a record of the
               tree, folded branches included, not a word on screen. -->
          <div class="codex-editor__search-row">
            <SearchField
              v-model="filter"
              v-model:active-scopes="activeScopes"
              :scopes="searchScopes"
              :placeholder="t('codex.editor.filter')"
              density="compact"
            />
            <!-- An unlabelled gear, as in the detail rail: it is about how the tree is shown, not a
                 page action. The menu stays open while its options are toggled. -->
            <VMenu location="bottom end" :offset="4" :close-on-content-click="false">
              <template #activator="{ props: menuProps, isActive }">
                <VBtn
                  v-bind="menuProps"
                  icon
                  variant="text"
                  class="codex-editor__gear"
                  :active="isActive"
                  :title="t('codex.editor.tree_settings')"
                  :aria-label="t('codex.editor.tree_settings')"
                >
                  <IconSettings :size="18" :stroke-width="1.6" />
                </VBtn>
              </template>
              <VCard variant="outlined" rounded="lg" class="codex-editor__settings">
                <VSwitch
                  v-model="settings.ui.codexShowDeleted"
                  :label="t('codex.editor.show_deleted')"
                  color="primary"
                  density="compact"
                  hide-details
                />
              </VCard>
            </VMenu>
          </div>
          <VDivider class="codex-editor__rule" />
          <div class="codex-editor__tree">
            <CodexTree
              :nodes="shownTree"
              :selected="code"
              :collapsed="shownCollapsed"
              :reorderable="!filter.trim()"
              :accepts="accepts"
              @drop="drop"
              @dragging="setDragging"
              @select="select"
              @toggle="toggle"
              @add="add"
              @move="move"
              @up="up"
              @down="down"
              @remove="remove"
              @restore="restore"
            />
            <p v-if="filter && !shownTree.length" class="codex-editor__muted">{{ t('codex.editor.filter_empty') }}</p>
          </div>
        </VCard>
        <div
          class="codex-editor__resize"
          role="separator"
          tabindex="0"
          aria-orientation="vertical"
          :aria-label="t('codex.editor.resize_nav')"
          :aria-valuenow="navWidth"
          :aria-valuemin="CODEX_NAV_WIDTH_MIN"
          :aria-valuemax="CODEX_NAV_WIDTH_MAX"
          @pointerdown="startResize"
          @keydown.left.prevent="resizeByKey(-1)"
          @keydown.right.prevent="resizeByKey(1)"
        />
      </div>

      <div class="codex-editor__main">
        <VAlert v-if="code && !loading && !inCanvas" type="warning" variant="tonal">
          {{ t('codex.editor.not_mounted') }}
          <template #append>
            <VBtn variant="text" :to="CODEX_AVAILABLE">{{ t('codex.editor.to_list') }}</VBtn>
          </template>
        </VAlert>

        <template v-else-if="codex || note">
          <!-- The record's heading opens its column, not the page: the navigation runs from the top
               of the page beside it. The title is edited right where it is read, as on the task
               page. -->
          <PageHeader :title="draft.title || t('codex.editor.title')">
            <template #title>
              <!-- The virtual path above the name — where the record sits in the canvas, the
                   address the agent reaches it by. A codex's path is its own segment. -->
              <div class="codex-editor__path">{{ openPath }}</div>
              <InvisibleField
                :model-value="draft.title"
                :placeholder="t('codex.form.name')"
                :aria-label="t('codex.form.name')"
                :maxlength="CODEX_TITLE_MAX"
                :error="!draft.title.trim()"
                class="codex-editor__title"
                @update:model-value="(value) => { draft.title = value; schedule() }"
                @blur="commit"
              />
            </template>
            <!-- "Copy the code" on the right of the heading — where other pages keep "Refresh", the
                 same button as the detail pages' (`DetailHead`). -->
            <template #actions>
              <!-- The path first: it names the place in the canvas, the code the record itself.
                   Copied as shown, with the leading slash — the agent's tools take it so. -->
              <VBtn variant="text" @click="copyText(openPath)">
                <template #prepend>
                  <IconCheck v-if="isCopied(openPath)" :size="16" class="codex-editor__copied" />
                  <IconCopy v-else :size="16" />
                </template>
                {{ t('codex.editor.copy_path') }}
              </VBtn>
              <CopyCodeButton :code="code" />
            </template>
          </PageHeader>

          <VCard variant="outlined" rounded="lg" class="codex-editor__card">
            <SectionHeader
              :title="t('codex.form.description')"
              :hint="t('codex.form.description_hint')"
            />
            <MarkdownEditor
              :model-value="draft.description"
              :aria-label="t('codex.form.description')"
              :max-length="CODEX_DESCRIPTION_MAX"
              mode="simple"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.description = value; schedule() }"
              @blur="commit"
            />
            <VDivider class="codex-editor__card-rule" />
            <VTextField
              :model-value="draft.segment"
              :label="t('codex.form.segment')"
              :maxlength="CODEX_SEGMENT_MAX"
              :error="!CODEX_SEGMENT_PATTERN.test(draft.segment) || !!segmentHolder"
              :error-messages="segmentHolder ? t('codex.editor.segment_taken', { title: segmentHolder.title }) : undefined"
              :hide-details="!segmentHolder"
              variant="outlined"
              class="codex-editor__segment"
              @update:model-value="onSegmentInput"
              @blur="commit"
            />
          </VCard>

          <VCard variant="outlined" rounded="lg" class="codex-editor__card">
            <SectionHeader
              :title="codex ? t('codex.editor.rules') : t('codex.editor.body')"
              :hint="codex ? t('codex.editor.rules_hint') : t('codex.editor.body_hint')"
            />
            <MarkdownEditor
              :model-value="draft.body"
              :aria-label="codex ? t('codex.editor.rules') : t('codex.editor.body')"
              :max-length="CODEX_BODY_MAX"
              :features="CODEX_DOCUMENT_FEATURES"
              :attach="attachToNote"
              :refuse="noteFileRefuse"
              variant="plain"
              min-height="0"
              @update:model-value="(value) => { draft.body = value; schedule() }"
              @blur="commit"
            />
          </VCard>

          <!-- A note holds files, a codex does not. -->
          <CodexNoteFiles v-if="note" :note-code="note.code" :disabled="Boolean(note.deleted_at)" />

          <p v-if="saveError" class="codex-editor__error">{{ saveError }}</p>
        </template>
      </div>
    </div>

    <AppDialog v-model="moveOpen" :title="t('codex.tree.move_title')" :description="moving?.title" size="base">
      <!-- Each target as its codex's badge, then its path and, quieter, its name — the path says
           where the note lands, the name which record that is. Searched by path, name and code. -->
      <VSelectSearch
        v-model="moveTarget"
        :items="moveTargets"
        :label="t('codex.tree.move_to')"
        :search-placeholder="t('codex.tree.move_search')"
        :no-data-text="t('codex.editor.filter_empty')"
        :chips="false"
        variant="outlined"
        hide-details
      >
        <template #item="{ props: itemProps, item }">
          <VListItem v-bind="itemProps" :title="item.path" :subtitle="item.name" class="codex-move__item">
            <template #prepend>
              <IconSwatch :icon="item.icon" :color="item.color" :width="20" />
            </template>
          </VListItem>
        </template>
        <template #selection="{ item }">
          <span class="codex-move__value">
            <IconSwatch :icon="item.icon ?? ''" :color="item.color ?? ''" :width="20" />
            {{ item.path }}
          </span>
        </template>
      </VSelectSearch>
      <template #actions>
        <VBtn variant="text" @click="moveOpen = false">{{ t('common.action.cancel') }}</VBtn>
        <VBtn color="primary" variant="flat" :disabled="!moveTarget" @click="confirmMove">
          {{ t('codex.tree.move') }}
        </VBtn>
      </template>
    </AppDialog>

    <!-- Reached from the keyboard too (D in the row menu): the confirm button holds the focus. -->
    <ConfirmDialog
      v-model="removeOpen"
      :title="removeDialog.title"
      :text="removeDialog.text"
      :confirm-label="removeDialog.confirm"
      focus-confirm
      @confirm="confirmRemove"
    />
  </PageLayout>
</template>

<style scoped>
/* The navigation keeps the width the person dragged it to while there is room; on a narrower
   screen it gives way first, down to 200px, so the record keeps at least 360px — its title, path
   and buttons must not be squeezed out. */
.codex-editor {
  display: grid;
  grid-template-columns: minmax(200px, var(--codex-nav-width, 300px)) minmax(360px, 1fr);
  gap: 24px;
  align-items: start;
}

@media (max-width: 900px) {
  .codex-editor { grid-template-columns: minmax(0, 1fr); }
}

/* A drag across the text would select it, and the cursor would flicker off the narrow handle. */
.codex-editor--resizing {
  cursor: col-resize;
  user-select: none;
}

/* The handle sits in the gap to the right of the navigation, centred on it. */
.codex-editor__resize {
  position: absolute;
  top: 0;
  bottom: 0;
  right: -16px;
  width: 8px;
  border-radius: 4px;
  cursor: col-resize;
  touch-action: none;
}

/* The pill is always visible: a handle that shows only under the pointer is never looked for. */
.codex-editor__resize::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 2px;
  width: 4px;
  height: 32px;
  border-radius: 2px;
  background: var(--border);
  transform: translateY(-50%);
  transition: background 0.12s ease;
}

.codex-editor__resize:hover::after,
.codex-editor__resize:focus-visible::after,
.codex-editor--resizing .codex-editor__resize::after { background: var(--accent); }

.codex-editor__resize:focus-visible { outline: none; }

@media (max-width: 900px) {
  .codex-editor__resize { display: none; }
}

.codex-editor__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.codex-editor__card { padding: 16px; }

/* The column's gap already spaces the heading from the first card. */
.codex-editor__main > .page-header { margin-bottom: 0; }

/* The segment closes the description card under a rule: both are about how the record is found —
   by the line the agent decides on, and by path. The rule runs edge to edge of the card. */
.codex-editor__card-rule {
  margin: 16px -16px;
}

.codex-editor__segment {
  max-width: 320px;
}

/* The header's text half shrinks to its content — for a field, its own default width, about half
   the column — and a longer title would be cut. Stretched as on the task page. */
.codex-editor__main > .page-header :deep(.section-header__text) {
  flex: 1 1 160px;
  min-width: 0;
}

/* On a narrow column the copy buttons go under the title rather than squeezing it to nothing. */
.codex-editor__main > .page-header :deep(.section-header) {
  flex-wrap: wrap;
  row-gap: 4px;
}

/* An empty title is not saved — the field has no frame to turn red, so its placeholder does: an
   empty heading must not read as an ordinary unfilled one. */
.codex-editor__title.v-input--error :deep(input::placeholder) {
  color: var(--error);
  opacity: 1;
}

/* The title as the page heading, as on the task page: the same size and weight as a static one. */
.codex-editor__title {
  width: 100%;
}

.codex-editor__title :deep(.v-field__input) {
  min-height: 28px;
  padding-block: 4px;
  margin-block: -4px;
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
  /* A title longer than the column ends in an ellipsis at rest rather than cut mid-letter; in the
     field under the caret the whole text scrolls as usual. */
  text-overflow: ellipsis;
}

/* The navigation stays in view while a long material scrolls, and never grows past the screen — as
   the rail of `DetailLayout`: the filter stays put, the tree scrolls by itself. The resize handle
   travels with it. With no page header above it, only the page's own padding (24px top and
   bottom) is taken off the height. */
.codex-editor__side {
  position: sticky;
  top: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 48px);
}

/* One column: the navigation stands above the record, so it is held to half a screen with its own
   scroll — a whole tree in front of the record would push the record thousands of pixels down. */
@media (max-width: 900px) {
  .codex-editor__side {
    position: static;
    max-height: 50vh;
  }
}

/* `min-height: 0` on both levels: a column-flex item's minimum height is its content, and without it
   the card would push past the limit instead of letting the tree scroll. */
.codex-editor__nav {
  padding: 12px;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* The search takes the row, the gear sits at its right edge. */
.codex-editor__search-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.codex-editor__search-row > :first-child {
  flex: 1;
  min-width: 0;
}

/* The gear as in the detail rail (`DetailNav`): a quiet 28px icon that lights only while open. */
.codex-editor__gear.v-btn {
  width: 28px;
  min-width: 28px;
  height: 28px;
  flex: none;
  color: var(--text-muted);
}

.codex-editor__gear.v-btn:hover { color: var(--text); }

.codex-editor__settings { padding: 4px 12px; }

/* The rule under the filter runs edge to edge of the card, as in the detail rail (`DetailNav`). */
.codex-editor__rule {
  flex: none;
  margin: 12px -12px 8px;
}

/* The tree runs edge to edge of the card, out of its 12px padding: the scrollbar then sits flush
   against the card's right edge instead of floating inside it, and the rows start close to the
   left edge — a tree is read by its indent, and the card's own padding only pushed every level
   right. */
.codex-editor__tree {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-inline: -12px;
  padding-inline: 4px 2px;
}

.codex-editor__muted {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.codex-editor__path {
  margin-bottom: 2px;
  font-size: 12px;
  line-height: 16px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* The check after copying stays grey, as on "Copy code" (`CopyCodeButton`): a routine action. */
.codex-editor__copied {
  color: var(--text-muted);
}

/* A move target: the path in the ordinary text color, the name under it muted. */
.codex-move__item :deep(.v-list-item-title) { color: var(--text); }
.codex-move__item :deep(.v-list-item-subtitle) {
  color: var(--text-muted);
  opacity: 1;
}

.codex-move__value {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.codex-editor__error {
  margin: 0;
  font-size: 12px;
  color: var(--error);
}

.codex-editor__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-height: 200px;
  justify-content: center;
  color: var(--text-muted);
}
</style>
