<script lang="ts">
/** One file in a holder's list. Domain-free: each holder maps its own rows to it. */
export interface AttachedFile {
  /** `FILE@…` — the code the text quotes it by. */
  code: string
  /** The holder's own name for the file; empty — it goes by the name it came under. */
  title: string
  /** What is inside the file. */
  description: string
  /** The name and extension the file came under. */
  originalName: string
  mime: string
  size: number
  /** Where inside the holder the file was attached, already worded; empty — the holder itself. */
  place?: string
}

export type { UploadFile, UploadOutcome } from './uploadQueue'

/** The address the backend shows a stored file at (`core_storage_view`): in a tab, inline. */
export function storedFileUrl(code: string): string {
  return `/storage/public/${encodeURIComponent(code.split('@').pop() ?? '')}`
}
</script>

<script setup lang="ts">
// The files a holder keeps — a section of the holder's page laid out as a task's notes are: a
// header on the canvas, then a card per file, two to a row. Each card says what the file is; the
// order is the one the person left. A click on a picture opens it full screen among the section's
// pictures; on any other file, in a new tab, where the browser shows what it can and offers to save
// the rest. «Скачать» in the card's menu saves it under the card's name.
//
// With `upload` the section takes files too: «Загрузить файлы» picks several, and files dragged
// from the computer drop anywhere on it. The section is a drop zone of the window's guard
// (`composables/useFileDrop.ts`): while files are over the window it wears a dashed mark, under the
// pointer it fills and says «Отпустите, чтобы добавить». They go one request per file, one at a
// time, in the order picked — so they land at the end in that order, as the holder lines new files
// up. Each waits, moves and ends in a card of its own below the files: a sent file leaves it for
// the list, a refused one keeps it with the reason until it is dismissed, a calm outcome (the file
// is there already) fades by itself. A folder and a file the holder refuses up front (`refuse`:
// over the size ceiling) never go out — their failed cards appear at once.
//
// A file that comes into the list — from this section, from a text field of the page, from the
// agent — flashes its card for 700 ms. The list the section starts with on a holder (`ready`) is
// not news and does not flash. A file this section sent is also scrolled into view; one a field
// sent is not: the person is looking at the field, where its code lands.
//
// The section outlives its holder (a page showing another task keeps it), so `upload` is the
// upload INTO `holder`, and a file takes both with it when it is queued (`uploadQueue.ts`): a file
// still waiting when the page moves on goes where it was dropped, and its card shows there only.
//
// The agent attaches files and never orders them: a new one lands at the end. Order is the
// person's — a card dragged by the handle, or W/S from its menu — and the whole order is saved at
// once, as with task notes. The cards render a local copy the library reorders the moment one is
// dropped, so a successful save changes nothing on screen; a fresh list from the holder replaces
// the copy.
//
// Without `upload` the section is not drawn while the holder has no files: an empty one would only
// say "nothing here" on every page. With it the empty section stays — it is where files are
// dropped — and says so in one card. The grid stays in the markup either way — the sortable is
// bound to it once, at mount.
//
// Deleting asks first: the file leaves the holder's list, and every `FILE@` / `IMAGE@` of it in the
// holder's text turns red. What goes is the holder's hold on the file (`detach`): where the same
// bytes are attached elsewhere, they stay there.
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDraggable } from 'vue-draggable-plus'
import { IconArrowBack, IconArrowForward, IconCloudUpload, IconDownload, IconExternalLink, IconPaperclip, IconTrash, IconX } from '@tabler/icons-vue'

import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DragHandle from '@/components/DragHandle.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { useFileDropZone } from '@/composables/useFileDrop'
import { useStorageStore } from '@/stores/storage'
import { carriesFiles, settleDropped, sortDropped, sortFiles, type SortedDrop } from '@/shared/utils/fileDrop'
import { mimeToName } from '@/shared/utils/mime-to-name'
import { revealInScroller } from '@/shared/utils/reveal'

import { downloadHref, startDownload } from './download'
import FileTile from './FileTile.vue'
import ImageGallery from './ImageGallery.vue'
import { placeShown } from './order'
import { createUploadQueue, type UploadFile, type UploadRow } from './uploadQueue'

/** Duration of the reorder animation — the library's stock FLIP. */
const ANIMATION_MS = 150

const props = defineProps<{
  files: AttachedFile[]
  /** What the files are for here — behind the "?" after the title. */
  hint?: string
  /** The holder is deleted: its files are read and opened, not moved, detached or added. */
  disabled?: boolean
  /** Send one file into the holder on screen; unset — the card takes no files. */
  upload?: UploadFile
  /** The holder on screen — its code; the rows of uploads are kept per holder. */
  holder?: string
  /** A file the holder will not take, known before sending: the reason; `null` — send it. */
  refuse?: (file: File) => string | null
  /**
   * `files` is the holder's list as read, not a stand-in while it loads. The first ready list of a
   * holder is what the card starts from; only files that come after it flash. Unset — ready.
   */
  ready?: boolean
  /** Which of `files` get a card; unset — all of them. The rest stay in the holder's order unseen. */
  shows?: (file: AttachedFile) => boolean
  /** Where dropped files land, in the holder's words — under the title while files are over the section. */
  dropNote?: string
}>()

const emit = defineEmits<{
  /** The whole order, top to bottom: the cards as they stand now, unseen files in their places. */
  reorder: [codes: string[]]
  /** The file is deleted from the holder — confirmed already. */
  detach: [code: string]
}>()

const { t, locale } = useI18n()

/** How many cards a folded section draws; the rest wait behind «Показать все». */
const FOLDED_COUNT = 4

const list = ref<HTMLElement | null>(null)
const items = ref<AttachedFile[]>([])
const expanded = ref(false)

// The files the section shows at all — the holder's filter (`shows`) applied. Folded, only the first
// of them get a card; the pictures full screen page through all of them, folded or not.
const listed = computed(() => (props.shows ? props.files.filter(props.shows) : props.files))
const foldable = computed(() => listed.value.length > FOLDED_COUNT)

watch(
  [listed, expanded],
  ([files, open]) => { items.value = open ? [...files] : files.slice(0, FOLDED_COUNT) },
  { immediate: true },
)

const sortable = useDraggable(list, items, {
  handle: '.drag-handle',
  draggable: '.attached-file',
  animation: ANIMATION_MS,
  // Pointer Events rather than native DnD, as everywhere in the app's lists.
  forceFallback: true,
  fallbackOnBody: true,
  fallbackTolerance: 4,
  ghostClass: 'attached-file--ghost',
  onEnd: (event) => {
    if (event.oldIndex === event.newIndex) return
    saveOrder()
  },
})

watch(() => props.disabled, (off) => { if (off) sortable.pause(); else sortable.resume() }, { immediate: true })

// Whole, with the unseen files in their places (`placeShown`).
function saveOrder(): void {
  emit('reorder', placeShown(props.files.map((file) => file.code), items.value.map((file) => file.code)))
}

/** Moving without a mouse: one place back or forward in the grid, saved the way a drop is. */
function shift(code: string, step: -1 | 1): void {
  const from = items.value.findIndex((file) => file.code === code)
  const to = from + step
  if (from < 0 || to < 0 || to >= items.value.length) return
  const next = [...items.value]
  const [file] = next.splice(from, 1)
  next.splice(to, 0, file)
  items.value = next
  saveOrder()
}

// ── What a card says ──────────────────────────────────────────────────────────
function nameOf(file: AttachedFile): string {
  return file.title || file.originalName || file.code
}

/** A picture's tile shows the picture itself (`FileTile`); any other file's, its kind's glyph. */
function pictureSrc(file: AttachedFile): string | undefined {
  return file.mime.startsWith('image/') ? storedFileUrl(file.code) : undefined
}

/**
 * The code "Copy code" puts in the clipboard — the word the text would show the file by: a picture
 * is pasted as `IMAGE@` and stands as a picture, any other file as `FILE@`, a link.
 */
function quotedCode(file: AttachedFile): string {
  return pictureSrc(file) ? `IMAGE@${file.code.slice(file.code.indexOf('@') + 1)}` : file.code
}

// Binary units, worded by the interface language: «1,5 КБ», «1.5 kB».
const SIZE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte'] as const

function sizeOf(bytes: number): string {
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  return new Intl.NumberFormat(locale.value, {
    style: 'unit',
    unit: SIZE_UNITS[unit],
    unitDisplay: 'short',
    maximumFractionDigits: unit === 0 ? 0 : 1,
  }).format(value)
}

/** What kind of file it is and how heavy: «PNG · 201 Б». */
function specOf(file: AttachedFile): string {
  return [mimeToName(file.mime, file.originalName), sizeOf(file.size)].filter(Boolean).join(' · ')
}

function openFile(file: AttachedFile): void {
  window.open(storedFileUrl(file.code), '_blank', 'noopener')
}

// ── Pictures full screen ──────────────────────────────────────────────────────
// A picture's card opens the picture full screen, with every picture shown in the section to page
// through, in the section's order (`ImageGallery`). Any other file opens in a tab; so does a
// picture from its menu, and its name clicked with a modifier or the middle button — the name is
// still a link.
const viewing = ref<string | null>(null)
const pictureCodes = computed(() => listed.value.filter((file) => pictureSrc(file)).map((file) => file.code))

function openCard(file: AttachedFile): void {
  if (pictureSrc(file)) viewing.value = file.code
  else openFile(file)
}

function onNameClick(event: MouseEvent, file: AttachedFile): void {
  event.stopPropagation()
  if (!pictureSrc(file) || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  viewing.value = file.code
}

// Saved under the name the card shows: here the name the file came under is known, so a file with
// no title goes to disk as it was brought in, not under its code.
function download(file: AttachedFile): void {
  const name = nameOf(file)
  startDownload(downloadHref(storedFileUrl(file.code), name), name)
}

// ── Upload ────────────────────────────────────────────────────────────────────
// A calm outcome is read and gone; a refusal waits for the person.
const NOTICE_MS = 8000

const holderKey = computed(() => props.holder ?? '')

// Another holder on the same page starts folded.
watch(holderKey, () => { expanded.value = false })

const queueState = reactive<{ rows: UploadRow[] }>({ rows: [] })
const queue = createUploadQueue(queueState, {
  noticeMs: NOTICE_MS,
  // The file this card sent is the one the person is waiting to see: shown, wherever it is.
  onOutcome: (holder, outcome) => {
    if (outcome.code && (outcome.ok || outcome.calm)) reveal(holder, outcome.code)
  },
})
const picker = ref<HTMLInputElement | null>(null)

// Uploads of other holders wait out of sight: their files go where they were dropped.
const uploads = computed(() => queue.rowsOf(holderKey.value))

const accepts = computed(() => Boolean(props.upload) && !props.disabled)

/**
 * Files on their way in: folders and the holder's own refusals become failed rows at once, the
 * rest are queued. The holder and its upload are taken now — the folder check may take a moment.
 */
async function take(sorted: SortedDrop): Promise<void> {
  const send = props.upload
  if (!accepts.value || !send) return
  const holder = holderKey.value
  const { files, folders } = await settleDropped(sorted)
  for (const name of folders) queue.refuse(holder, name, '', t('common.file_drop.folder'))
  const sendable: File[] = []
  for (const file of files) {
    const refusal = props.refuse?.(file) ?? null
    if (refusal) queue.refuse(holder, file.name, file.type, refusal)
    else sendable.push(file)
  }
  if (sendable.length) queue.enqueue(holder, send, sendable)
}

function dismiss(id: number): void {
  queue.dismiss(id)
}

function pick(): void {
  picker.value?.click()
}

function picked(event: Event): void {
  const input = event.target as HTMLInputElement
  void take(sortFiles(Array.from(input.files ?? [])))
  // The same file picked again must fire `change` again.
  input.value = ''
}

// The window's guard sets the drop effect and keeps a drop beside the section from opening the
// file; the section only takes the drop it accepted. The cards reorder by pointer events, not
// native drag, and a dragged piece of text is not a file: neither reaches here.
const section = ref<HTMLElement | null>(null)
const zone = useFileDropZone(section, () => accepts.value)

function drop(event: DragEvent): void {
  if (!carriesFiles(event.dataTransfer?.types)) return
  event.preventDefault()
  // The items of a drop live as long as the event: the folders are told apart now.
  void take(sortDropped(event.dataTransfer))
}

// ── What the drop mark says ───────────────────────────────────────────────────
// Over the section the person is told what will happen before letting go: how many files go, where
// they land (the holder's words) and what will not be taken. The browser tells how many items a
// drag carries while it is still in the air — not their names; a folder counts as one.
const storage = useStorageStore()
const carried = ref(0)

function countCarried(event: DragEvent): void {
  const items = event.dataTransfer?.items
  carried.value = items ? [...items].filter((item) => item.kind === 'file').length : 0
}

const dropTitle = computed(() =>
  carried.value > 0
    ? t('common.attached_files.drop.title', carried.value)
    : t('common.attached_files.drop.title_unknown'))

const MEBIBYTE = 1024 * 1024

const dropLimits = computed(() => {
  const limit = storage.maxFileSize
  return limit === null
    ? t('common.attached_files.drop.limits_unknown')
    : t('common.attached_files.drop.limits', { mb: Math.floor(limit / MEBIBYTE) })
})

const shown = computed(() => items.value.length > 0 || uploads.value.length > 0 || accepts.value)

// ── Arrival ───────────────────────────────────────────────────────────────────
// Matches the editor's moved-block flash and the research's confirmation: 700 ms, background only.
const FLASH_MS = 700

const flashing = ref(new Set<string>())
const timers = new Map<string, ReturnType<typeof setTimeout>>()
// The codes the card has shown on this holder; `null` — no ready list of it yet.
let seen: Set<string> | null = null
let seenHolder: string | null = null
// Files this card sent, waiting to be shown once the holder's list has them.
const toReveal = new Map<string, string>()

function flash(code: string): void {
  clearTimeout(timers.get(code))
  const next = new Set(flashing.value)
  // A card flashing already starts over: the class comes off for a frame, then back.
  next.delete(code)
  flashing.value = next
  void nextTick(() => {
    flashing.value = new Set(flashing.value).add(code)
    timers.set(code, setTimeout(() => {
      const rest = new Set(flashing.value)
      rest.delete(code)
      flashing.value = rest
      timers.delete(code)
    }, FLASH_MS))
  })
}

function cardOf(code: string): Element | null {
  return list.value?.querySelector(`[data-code="${CSS.escape(code)}"]`) ?? null
}

// A file this section sent that landed past the folded cards unfolds the section: the person is
// waiting to see it. It is shown once the cards are drawn (`watch(items)` below).
function revealPending(): void {
  for (const [code, holder] of toReveal) {
    if (holder !== holderKey.value || !listed.value.some((file) => file.code === code)) continue
    if (!items.value.some((file) => file.code === code)) {
      expanded.value = true
      continue
    }
    toReveal.delete(code)
    if (!flashing.value.has(code)) flash(code)
    const card = cardOf(code)
    if (card) revealInScroller(card)
  }
}

function reveal(holder: string, code: string): void {
  toReveal.set(code, holder)
  revealPending()
}

watch(items, revealPending, { flush: 'post' })

watch(
  () => [holderKey.value, props.files, props.ready !== false] as const,
  ([holder, files, ready]) => {
    if (!ready) return
    const codes = new Set(files.map((file) => file.code))
    if (seen !== null && seenHolder === holder) {
      for (const code of codes) if (!seen.has(code)) flash(code)
    }
    seen = codes
    seenHolder = holder
    revealPending()
  },
  { immediate: true, flush: 'post' },
)

onBeforeUnmount(() => {
  for (const timer of timers.values()) clearTimeout(timer)
})

function percent(share: number): number {
  return Math.round(Math.min(1, Math.max(0, share)) * 100)
}

// ── Delete ────────────────────────────────────────────────────────────────────
// The file outlives the open flag: while the dialog fades out it keeps its own text.
const deleting = ref<AttachedFile | null>(null)
const confirmOpen = ref(false)

function ask(file: AttachedFile): void {
  deleting.value = file
  confirmOpen.value = true
}

function remove(): void {
  confirmOpen.value = false
  if (deleting.value) emit('detach', deleting.value.code)
}

const confirmText = computed(() =>
  t('common.attached_files.delete_confirm.text', { name: deleting.value ? nameOf(deleting.value) : '' }),
)

// ── Menu ──────────────────────────────────────────────────────────────────────
const openMenu = ref<string | null>(null)
const menus = new Map<string, InstanceType<typeof ActionMenu>>()

function setMenu(code: string, open: boolean): void {
  if (open) openMenu.value = code
  else if (openMenu.value === code) openMenu.value = null
}

function bindMenu(code: string, menu: unknown): void {
  if (menu) menus.set(code, menu as InstanceType<typeof ActionMenu>)
  else menus.delete(code)
}

function menuItems(file: AttachedFile): ActionMenuItem[] {
  const menu: ActionMenuItem[] = [
    { key: 'open', icon: IconExternalLink, label: t('common.attached_files.open'), hotkey: 'T', run: () => openFile(file) },
    { key: 'download', icon: IconDownload, label: t('common.attached_files.download'), run: () => download(file) },
  ]
  if (props.disabled) return menu
  // W and S move, as on a note card; in a grid "up" is the place before, "down" the place after.
  const at = items.value.findIndex((candidate) => candidate.code === file.code)
  menu.push(
    { key: 'delete', icon: IconTrash, label: t('common.attached_files.delete'), danger: true, hotkey: 'D', divider: true, run: () => ask(file) },
    { key: 'back', icon: IconArrowBack, label: t('common.attached_files.move_back'), hotkey: 'W', divider: true, disabled: at === 0, run: () => shift(file.code, -1) },
    { key: 'forward', icon: IconArrowForward, label: t('common.attached_files.move_forward'), hotkey: 'S', disabled: at === items.value.length - 1, run: () => shift(file.code, 1) },
  )
  return menu
}
</script>

<template>
  <section
    ref="section"
    v-show="shown"
    class="attached-files"
    :class="{ 'attached-files--armed': zone.armed.value, 'attached-files--over': zone.over.value }"
    @dragenter="countCarried"
    @dragover="countCarried"
    @drop="drop"
  >
    <SectionHeader
      :title="t('common.attached_files.section')"
      :hint="hint"
      class="attached-files__header"
    >
      <!-- `actions`: what else acts on the whole set — a filter of the holder's — left of add. -->
      <template v-if="upload || $slots.actions" #right>
        <slot name="actions" />
        <VBtn v-if="upload" variant="text" size="small" :disabled="disabled" class="attached-files__add" @click="pick">
          <template #prepend><IconPaperclip :size="16" /></template>
          {{ t('common.attached_files.add') }}
        </VBtn>
        <input
          v-if="upload"
          ref="picker"
          type="file"
          multiple
          hidden
          class="attached-files__picker"
          @change="picked"
        >
      </template>
    </SectionHeader>

    <VCard
      v-if="accepts && !items.length && !uploads.length"
      tag="p"
      variant="outlined"
      rounded="lg"
      class="attached-files__empty"
    >
      {{ t('common.attached_files.empty') }}
    </VCard>

    <!-- Always in the markup, empty or not: the sortable is bound to this element once, at mount. -->
    <div ref="list" class="attached-files__grid" role="list" :aria-label="t('common.attached_files.list')">
      <VCard
        v-for="file in items"
        :key="file.code"
        :data-code="file.code"
        class="attached-file drag-row"
        :class="{
          'attached-file--menu': openMenu === file.code,
          'attached-file--flash': flashing.has(file.code),
        }"
        variant="outlined"
        rounded="lg"
        link
        role="listitem"
        @click="openCard(file)"
        @contextmenu="menus.get(file.code)?.openAt($event)"
      >
        <span class="attached-file__flash" aria-hidden="true" />
        <DragHandle
          class="attached-file__handle"
          :class="{ 'attached-file__handle--off': disabled }"
          :label="t('common.attached_files.drag')"
          always
          @click.stop
        />
        <FileTile :name="file.originalName" :mime="file.mime" :src="pictureSrc(file)" class="attached-file__tile" />
        <a
          class="attached-file__name"
          :href="storedFileUrl(file.code)"
          target="_blank"
          rel="noopener"
          :title="nameOf(file)"
          @click="onNameClick($event, file)"
        >{{ nameOf(file) }}</a>
        <ActionMenu
          :ref="(menu) => bindMenu(file.code, menu)"
          class="attached-file__menu"
          :open="openMenu === file.code"
          :items="menuItems(file)"
          :code="quotedCode(file)"
          :label="t('common.attached_files.actions')"
          @update:open="setMenu(file.code, $event)"
        />
        <p v-if="file.description" class="attached-file__description">{{ file.description }}</p>
        <span v-if="file.place" class="attached-file__meta attached-file__place">{{ file.place }}</span>
        <span class="attached-file__spec">{{ specOf(file) }}</span>
      </VCard>
    </div>

    <div v-if="foldable" class="attached-files__more">
      <VBtn variant="text" size="small" @click="expanded = !expanded">
        {{ expanded ? t('common.attached_files.fold') : t('common.attached_files.show_all', { count: listed.length }) }}
      </VBtn>
    </div>

    <ul
      v-if="uploads.length"
      class="attached-files__grid attached-files__uploads"
      :class="{ 'attached-files__uploads--after': items.length }"
      :aria-label="t('common.attached_files.uploads')"
    >
      <VCard
        v-for="item in uploads"
        :key="item.id"
        tag="li"
        variant="outlined"
        rounded="lg"
        class="attached-file attached-upload"
        :class="`attached-upload--${item.state}`"
      >
        <FileTile :name="item.name" :mime="item.mime" class="attached-file__tile" />
        <span class="attached-file__name" :title="item.name">{{ item.name }}</span>
        <VBtn
          v-if="item.state === 'failed' || item.state === 'notice'"
          icon
          variant="text"
          size="x-small"
          class="attached-file__menu"
          :aria-label="t('common.attached_files.dismiss')"
          @click="dismiss(item.id)"
        >
          <IconX :size="16" />
        </VBtn>
        <VProgressLinear
          v-if="item.state === 'sending'"
          :model-value="percent(item.share)"
          color="primary"
          height="4"
          rounded
          class="attached-upload__bar"
          :aria-label="item.name"
        />
        <span v-if="item.state === 'queued'" class="attached-file__meta">{{ t('common.attached_files.queued') }}</span>
        <span v-else-if="item.state === 'sending'" class="attached-file__meta">{{ percent(item.share) }}%</span>
        <span v-else class="attached-file__meta attached-upload__text" role="status">{{ item.text }}</span>
      </VCard>
    </ul>

    <div v-if="accepts" class="attached-files__drop" aria-hidden="true">
      <div class="attached-files__drop-body">
        <span class="attached-files__drop-icon"><IconCloudUpload :size="28" :stroke-width="1.6" /></span>
        <p class="attached-files__drop-title">{{ dropTitle }}</p>
        <p v-if="dropNote" class="attached-files__drop-note">{{ dropNote }}</p>
        <p class="attached-files__drop-limits">{{ dropLimits }}</p>
      </div>
    </div>

    <ImageGallery v-model="viewing" :codes="pictureCodes" />

    <ConfirmDialog
      v-model="confirmOpen"
      :title="t('common.attached_files.delete_confirm.title')"
      :text="confirmText"
      :confirm-label="t('common.attached_files.delete_confirm.confirm')"
      enter-confirms
      focus-confirm
      @confirm="remove"
    />
  </section>
</template>

<style scoped>
/* The frame of the drop marks (`::after`, `__drop`): the whole section, header included. */
.attached-files {
  position: relative;
  /* How far the drop marks stand outside the section (see below). */
  --attached-files-outset: 6px;
}

/* On the canvas, as the notes' header (`CollectionHeader`): the title inset to the line of the
   titles inside the cards above it — their border and 16px padding. */
.attached-files__header { padding-inline-start: 17px; }

/* Two to a row, as the notes: half of the column holds a name, a few lines about the file and what
   it is without cutting them to a word. Narrow screens — one. */
.attached-files__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (max-width: 600px) {
  .attached-files__grid { grid-template-columns: minmax(0, 1fr); }
}

.attached-files__uploads--after { margin-top: 12px; }

/* «Показать все» / «Свернуть» — under the cards, centred: it belongs to the whole list, not to the
   card it happens to stand under. */
.attached-files__more {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}

/* The note card's anatomy with the file's glyph after the handle: handle, glyph, name and "⋯" on
   the first line, the description and the place under the name, the kind and weight in the bottom
   right corner. The padding is the note's: the handle's box on the left and the "⋯" button's on the
   right make up the rest.

   The rows are numbered — head, description, place, corner — and the last takes whatever height the
   grid's row gives the card beyond its content, so the corner sits on the card's own bottom edge
   however tall its neighbour makes it. No `row-gap`: a row without its line would still keep its
   gaps; the lines carry their own top margin instead. */
.attached-file {
  position: relative;
  display: grid;
  grid-template-columns: 20px 44px minmax(0, 1fr) auto;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  column-gap: 4px;
  min-height: 72px;
  padding: 12px 8px;
}

.attached-file__handle { grid-area: 1 / 1; }

/* On a deleted holder the handle keeps its place unseen, so the cards read as they do elsewhere. */
.attached-file__handle--off { visibility: hidden; }

/* While its menu is open the card stays as it looks under the pointer: the pointer has gone onto
   the items, and only this mark says which file they will act on. */
.attached-file--menu { border-color: var(--gc-ink, var(--accent)); }

/* The file's tile (`FileTile`), as tall as the name's two lines; the text keeps one column to the
   right of it. */
.attached-file__tile {
  grid-area: 1 / 2 / 3 / 3;
  align-self: start;
  margin-top: 2px;
}

/* Two lines before the ellipsis, as a note's title: a long name still leaves room for what the
   file is. The card itself is the hover mark, so the link is not underlined. */
.attached-file__name {
  grid-area: 1 / 3;
  padding-top: 4px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  color: inherit;
  text-decoration: none;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.attached-file__name:hover { text-decoration: none; }

.attached-file__menu { grid-area: 1 / 4; }

/* Three lines at most, as a note's description: what is inside, the file itself says the rest. */
.attached-file__description {
  grid-area: 2 / 3;
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.attached-file__meta {
  grid-column: 3;
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted);
}

.attached-file__place { grid-row: 3; }

/* The kind and weight are looked up, not read: small and the quietest grey, out of the text's way
   in the corner, under the "⋯" column's right edge. */
.attached-file__spec {
  grid-area: 4 / 3 / 5 / 5;
  justify-self: end;
  align-self: end;
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-faint);
  white-space: nowrap;
}

.attached-file--ghost { opacity: 0.4; }

/* The empty section's one line, in a card where the first file's will stand. */
.attached-files__empty {
  margin: 0;
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-muted);
}

/* An upload is a card where its file's will stand: the handle's column stays empty. */
.attached-upload__bar {
  grid-column: 3;
  margin: 6px 0 2px;
}

.attached-upload--failed .attached-upload__text { color: rgb(var(--v-theme-error)); }

/* Files over the window: a dashed line around the section says "this takes files" before the
   person aims. Under the pointer the line goes solid and the section fills — the one place the drop
   lands. Both are layers that fade by `opacity` alone; nothing moves the layout. They stand a little
   outside the section: at its edge the line would run along the outer cards' own borders and read
   as theirs. */
.attached-files::after {
  content: '';
  position: absolute;
  inset: calc(-1 * var(--attached-files-outset));
  border: 1px dashed var(--accent);
  border-radius: calc(var(--radius) + var(--attached-files-outset));
  opacity: 0;
  pointer-events: none;
  transition: opacity 150ms ease;
}

.attached-files--armed::after { opacity: 1; }

.attached-files--over::after {
  border: 2px solid rgb(var(--v-theme-primary));
}

.attached-files__drop {
  position: absolute;
  inset: calc(-1 * var(--attached-files-outset));
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: calc(var(--radius) + var(--attached-files-outset));
  /* Near-opaque, so the cards under it do not read through what it says, and tinted with the
     accent: the section is now a place things go into, not a list. */
  background:
    linear-gradient(var(--accent-soft), var(--accent-soft)),
    color-mix(in srgb, var(--surface) 97%, transparent);
  opacity: 0;
  pointer-events: none;
  transition: opacity 350ms cubic-bezier(0.15, 1, 0.3, 1);
}

.attached-files--over .attached-files__drop { opacity: 1; }

/* What happens, top to bottom: the sign, the act, where the files land, what is not taken. It
   settles in from a little smaller as the mark appears. */
.attached-files__drop-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  max-width: 380px;
  padding: 16px;
  text-align: center;
  transform: scale(0.96);
  transition: transform 350ms cubic-bezier(0.15, 1, 0.3, 1);
}

.attached-files--over .attached-files__drop-body { transform: none; }

.attached-files__drop-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin-bottom: 8px;
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-radius: 50%;
  background: var(--surface);
  color: var(--accent);
  box-shadow: 0 6px 20px rgb(0 0 0 / 8%);
}

/* The sign floats while the files are held over the section: it waits for them. */
.attached-files--over .attached-files__drop-icon {
  animation: attached-files-float 1.4s ease-in-out infinite alternate;
}

@keyframes attached-files-float {
  from { transform: translateY(0); }
  to   { transform: translateY(-4px); }
}

.attached-files__drop-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  color: var(--text);
}

.attached-files__drop-note {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-muted);
}

.attached-files__drop-limits {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-faint);
}

/* A file that just came in: its card's background flashes and fades, 700 ms — after a drop the eye
   loses the new card among the others. A layer of its own, faded by `opacity`: a clickable card's
   `::before` and `::after` are Vuetify's. */
.attached-file__flash {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--accent-soft);
  opacity: 0;
  pointer-events: none;
}

.attached-file--flash .attached-file__flash {
  animation: attached-file-flash 700ms cubic-bezier(0.25, 0.1, 0.25, 1) forwards;
}

@keyframes attached-file-flash {
  from { opacity: 1; }
  to   { opacity: 0; }
}

/* Without motion the mark still comes and goes — held whole for the same time, then gone. */
@media (prefers-reduced-motion: reduce) {
  .attached-files::after,
  .attached-files__drop,
  .attached-files__drop-body { transition: none; }
  .attached-files--over .attached-files__drop-icon { animation: none; }
  .attached-file--flash .attached-file__flash { animation-timing-function: steps(1, end); }
}
</style>
