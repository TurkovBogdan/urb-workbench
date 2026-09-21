<script setup lang="ts">
// Журнал работы: решения, замечания, находки и факты одной лентой.
//
// Лента дописываемая — правки записей нет вовсе, как и на бэке. Закрыть запись можно один раз:
// поле разрешения показывается только у открытой, а у закрытой стоит текстом. Передумали — новая
// запись; так и устроен журнал.
//
// Виды записей не разведены по вкладкам: их четыре, и лента читается временем, а не разделами.
// Вид виден шильдиком, а фильтр «только открытые» отвечает на единственный вопрос, ради которого
// журнал листают в работе — «что ещё висит».
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
  /** Задача в корзине: журнал только читается. */
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

/** Открытая запись — та, у которой пусто разрешение. Факт закрыт в момент создания. */
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
 * Закрыть запись. Пустое разрешение бэк не примет — это и есть смысл «закрыть».
 *
 * Закрытие приходит с двух событий сразу: Enter закрывает запись, а следом поле теряет фокус и
 * тем же текстом присылает `blur`. Второй заход упёрся бы в дописываемость журнала и показал
 * пользователю «запись уже закрыта» на его же успешное действие, — поэтому код помечается
 * отправленным ДО запроса и повторный вызов молча отваливается.
 */
const submitted = new Set<string>()

async function resolve(note: NoteRow, value: string) {
  const text = value.trim()
  if (!text || submitted.has(note.code)) return
  submitted.add(note.code)
  // Отказ снимает пометку: иначе упавший запрос навсегда запер бы запись открытой.
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

    <!-- Форма заведения раскрывается по кнопке, а не стоит всегда: журнал чаще читают, чем
         пополняют, и постоянная форма съедала бы первый экран ленты. -->
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
      <!-- Запись журнала — тот же документ, что и план: в неё кладут разбор со списками,
           листингами и ссылками на соседние сущности. Потолок при этом вчетверо ниже, и
           счётчик об этом говорит. -->
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

      <!-- Тело записи набирают разметкой, а показывалось оно сырым текстом: списки шли дефисами
           в строку, а код — бэктиками. Правки у записи нет (лента дописываемая), поэтому здесь
           рендерер, а не редактор. -->
      <MarkdownRenderer v-if="note.body" :text="note.body" compact class="entry__body" />

      <!-- Разрешение у закрытой записи стоит текстом: переписать его нельзя, и поле ввода тут
           обещало бы правку, которой нет. -->
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

/* Открытая запись помечена полосой слева, а не цветом всей карточки: цветных карточек в ленте
   было бы столько же, сколько записей, и пометка перестала бы работать. */
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

/* Кегль, интерлиньяж и зазоры даёт компактный вид рендерера — он для того и есть: интерфейсный
   хром, а не зона чтения. Здесь остаётся только то, чего у него нет: запись в ленте вторична по
   отношению к своему заголовку, поэтому приглушена. */
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
