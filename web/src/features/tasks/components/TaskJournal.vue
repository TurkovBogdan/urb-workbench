<script setup lang="ts">
// The work journal: decisions, remarks, findings and facts in one feed.
//
// The feed is append-only — entries cannot be edited at all, same as on the backend. An entry can
// be closed once: the resolution field is shown only on an open entry, and on a closed one it is
// plain text. Changed your mind — write a new entry; that is how the journal works.
//
// Entry kinds are not split into tabs: there are four, and the feed reads by time, not by section.
// The kind shows as a badge, and the "open only" filter answers the one question the journal is
// scrolled for during work — "what is still pending".
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconPlus } from '@tabler/icons-vue'

import StatusBadge from '@/components/StatusBadge.vue'
import MarkdownRenderer from '@/components/markdown/renderer/MarkdownRenderer.vue'
import { MarkdownEditor } from '@/components/markdown/editor'
import { errorText } from '@/api/errorText'
import { fmtDateTime } from '@/shared/utils/date'

import { createNote, resolveNote, type NoteRow } from '../api'
import { TASK_DOCUMENT_FEATURES } from '../editor'
import {
  NOTE_BODY_MAX,
  NOTE_RESOLUTION_MAX,
  NOTE_TYPES,
  TASK_TITLE_MAX,
  noteColor,
} from '../labels'

const props = defineProps<{
  taskCode: string
  notes: NoteRow[]
  /** The task is in the trash: the journal is read-only. */
  disabled?: boolean
}>()

const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()

const openOnly = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)

const adding = ref(false)
const draftType = ref<string>(NOTE_TYPES[0])
const draftTitle = ref('')
const draftBody = ref('')

const typeItems = computed(() =>
  NOTE_TYPES.map((value) => ({ value, title: t(`tasks.note.type.${value}`) })),
)

/** An open entry is one with an empty resolution. A fact is closed at creation. */
const isOpen = (note: NoteRow) => note.resolution === ''

const visible = computed(() =>
  openOnly.value ? props.notes.filter(isOpen) : props.notes,
)

const openCount = computed(() => props.notes.filter(isOpen).length)

async function run(action: () => Promise<unknown>) {
  busy.value = true
  error.value = null
  try {
    await action()
    emit('changed')
    return true
  } catch (e) {
    error.value = errorText(e)
    return false
  } finally {
    busy.value = false
  }
}

async function add() {
  if (!draftTitle.value.trim()) return
  const ok = await run(() =>
    createNote(
      props.taskCode,
      { type: draftType.value, title: draftTitle.value.trim(), body: draftBody.value },
      { report: false },
    ),
  )
  if (!ok) return
  draftTitle.value = ''
  draftBody.value = ''
  adding.value = false
}

/**
 * Close an entry. The backend rejects an empty resolution — that is exactly what "close" means.
 *
 * Closing arrives from two events at once: Enter closes the entry, then the field loses focus and
 * sends `blur` with the same text. The second pass would hit the journal's append-only rule and
 * show the user "entry already closed" for their own successful action — so the code is marked as
 * submitted BEFORE the request and a repeated call silently drops out.
 */
const submitted = new Set<string>()

async function resolve(note: NoteRow, value: string) {
  const text = value.trim()
  if (!text || submitted.has(note.code)) return
  submitted.add(note.code)
  // A refusal clears the mark: otherwise a failed request would lock the entry open forever.
  if (!(await run(() => resolveNote(note.code, text, { report: false })))) {
    submitted.delete(note.code)
  }
}
</script>

<template>
  <div class="journal">
    <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>

    <div class="journal__bar">
      <VSwitch
        v-model="openOnly"
        :label="t('tasks.note.open_only', { count: openCount })"
        color="primary"
        density="compact"
        hide-details
        class="journal__filter"
      />
      <VBtn variant="text" size="small" :disabled="props.disabled || busy" @click="adding = !adding">
        <template #prepend><IconPlus :size="16" /></template>
        {{ t('tasks.note.add') }}
      </VBtn>
    </div>

    <!-- The add form expands on a button press rather than always being there: the journal is read
         more often than added to, and a permanent form would eat the first screen of the feed. -->
    <div v-if="adding" class="journal__form">
      <VSelect
        v-model="draftType"
        :items="typeItems"
        :label="t('tasks.note.type_label')"
        variant="outlined"
        density="compact"
        hide-details
      />
      <VTextField
        v-model="draftTitle"
        :label="t('tasks.note.title')"
        :maxlength="TASK_TITLE_MAX"
        variant="outlined"
        density="compact"
        hide-details
        autofocus
      />
      <!-- A journal entry is the same kind of document as the plan: it holds analysis with lists,
           code listings and references to neighbouring entities. Its cap is four times lower,
           though, and the counter says so. -->
      <MarkdownEditor
        v-model="draftBody"
        :label="t('tasks.note.body')"
        :max-length="NOTE_BODY_MAX"
        :features="TASK_DOCUMENT_FEATURES"
        min-height="0"
      />
      <div class="journal__form-actions">
        <VBtn variant="text" size="small" :disabled="busy" @click="adding = false">
          {{ t('common.action.cancel') }}
        </VBtn>
        <VBtn
          color="primary"
          variant="flat"
          size="small"
          :loading="busy"
          :disabled="!draftTitle.trim()"
          @click="add"
        >
          {{ t('common.action.add') }}
        </VBtn>
      </div>
    </div>

    <p v-if="!visible.length" class="journal__empty">
      {{ openOnly ? t('tasks.note.empty_open') : t('tasks.note.empty') }}
    </p>

    <article v-for="note in visible" :key="note.code" class="entry" :class="{ 'entry--open': isOpen(note) }">
      <header class="entry__head">
        <StatusBadge :color="noteColor(note.type)">{{ t(`tasks.note.type.${note.type}`) }}</StatusBadge>
        <span class="entry__title">{{ note.title }}</span>
        <span class="entry__date">{{ fmtDateTime(note.created_at) }}</span>
      </header>

      <!-- The entry body is written in markdown but used to be shown as raw text: lists came out as
           inline dashes and code as backticks. An entry cannot be edited (the feed is
           append-only), so this is a renderer, not an editor. -->
      <MarkdownRenderer v-if="note.body" :text="note.body" compact class="entry__body" />

      <!-- A closed entry's resolution is plain text: it cannot be rewritten, and an input field
           here would promise an edit that does not exist. -->
      <p v-if="note.resolution" class="entry__resolution">
        <span class="entry__resolution-label">{{ t('tasks.note.resolution') }}:</span>
        {{ note.resolution }}
      </p>

      <VTextField
        v-else
        :label="t('tasks.note.resolve')"
        :maxlength="NOTE_RESOLUTION_MAX"
        :disabled="props.disabled || busy"
        variant="outlined"
        density="compact"
        hide-details
        class="entry__resolve"
        @keyup.enter="(event: KeyboardEvent) => resolve(note, (event.target as HTMLInputElement).value)"
        @blur="(event: FocusEvent) => resolve(note, (event.target as HTMLInputElement).value)"
      />
    </article>
  </div>
</template>

<style scoped>
.journal {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.journal__bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.journal__filter { flex: none; }

.journal__filter :deep(.v-selection-control:not(.v-selection-control--dirty) .v-label) {
  opacity: var(--v-medium-emphasis-opacity);
}

.journal__form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}

.journal__form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.journal__empty {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.entry {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
}

/* An open entry is marked by a stripe on the left, not by coloring the whole card: there would be
   as many colored cards in the feed as entries, and the mark would stop working. */
.entry--open { border-left: 2px solid var(--warn, var(--primary)); }

.entry__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.entry__title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.entry__date {
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}

/* Font size, line height and spacing come from the renderer's compact mode — that is what it is
   for: UI chrome, not a reading zone. Only what it lacks stays here: an entry in the feed is
   secondary to its title, so it is muted. */
.entry__body {
  margin: 0;
  color: var(--text-muted);
}

.entry__resolution {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text);
}

.entry__resolution-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-faint);
}

.entry__resolve { max-width: 520px; }
</style>
