<script setup lang="ts">
// The change feed indicator: a small faint line in the top right corner.
//
// It is for those who know where to look — it must not distract anyone else. So it is tiny, grey,
// doesn't catch the pointer and lives ~2 seconds: a spinner and "what was updated", then it fades.
// Only the latest occurrence is ever shown — the feed can be frequent, and a queue of messages
// would turn a quiet sign into flicker.
//
// The entity name is shown as is (`tasks.task`): the feed doesn't know entities, and a label for
// each would have every module add one — for a line that only the developer and the agent look at.
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useChangesStore, type Change } from '@/stores/changes'

/** How long the line stays visible after the latest occurrence. */
const VISIBLE_MS = 2000

/** How many codes to show; the rest as a number, otherwise a bulk change would fill half the screen. */
const IDS_SHOWN = 1

const { t } = useI18n()
const changes = useChangesStore()

const text = ref('')
const visible = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function describe(change: Change | null): string {
  if (!change) return t('common.changes.resync')
  const shown = change.ids.slice(0, IDS_SHOWN).join(', ')
  const more = change.ids.length > IDS_SHOWN ? ` +${change.ids.length - IDS_SHOWN}` : ''
  const ids = shown ? ` ${shown}${more}` : ''
  return `${t(`common.changes.event.${change.event}`)} · ${change.entity}${ids}`
}

watch(
  () => changes.latest?.seq,
  () => {
    if (!changes.latest) return
    text.value = describe(changes.latest.change)
    visible.value = true
    clearTimeout(timer)
    timer = setTimeout(() => { visible.value = false }, VISIBLE_MS)
  },
)

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <!-- A polite announcement for screen readers: it doesn't interrupt but waits until the person
       is done. What is shown and what is spoken are the same line. -->
  <Transition name="changes-indicator">
    <div v-if="visible" class="changes-indicator" role="status" aria-live="polite">
      <VProgressCircular indeterminate size="9" width="1.5" class="changes-indicator__spin" />
      <span class="changes-indicator__text">{{ text }}</span>
    </div>
  </Transition>
</template>

<style scoped>
/* A corner, not the page flow: the line floats over the header and shifts nothing. It doesn't
   catch the pointer — header buttons can sit under it. */
.changes-indicator {
  position: fixed;
  top: 6px;
  right: 14px;
  z-index: 2000;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 50vw;
  font-family: var(--font);
  font-size: 10px;
  line-height: 12px;
  color: var(--text-faint);
  opacity: 0.8;
  pointer-events: none;
  user-select: none;
}

/* Against the accent every spinner gets (theme defaults in `plugins/vuetify.ts`, the global
   `.v-progress-circular` rule in main.scss): here it must be as grey as the text, otherwise an
   orange dot in the corner draws the eye more than the whole line. */
.changes-indicator__spin {
  flex: none;
  color: var(--text-faint);
}

.changes-indicator__text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.changes-indicator-enter-active,
.changes-indicator-leave-active {
  transition: opacity 200ms ease;
}

.changes-indicator-enter-from,
.changes-indicator-leave-to {
  opacity: 0;
}
</style>
