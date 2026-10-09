<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  IconAlertCircle, IconAlertTriangle, IconCheck, IconInfoCircle, IconX, type Icon,
} from '@tabler/icons-vue'
import { dismissToast, toasts, type ToastLevel } from '@/composables/useToasts'

// Toast display: one at a time, bottom right, on top of everything. `useToasts` holds the queue;
// this is the display and the countdown to auto-close.
//
// Color comes from palette TOKENS, not the Vuetify palette (`color="error"` paints solid):
// a soft fill, a border of the same tone, plain text, only the icon is tinted. The light theme
// comes for free — the tokens are already overridden there.
//
// We count the time down ourselves rather than via VSnackbar's `:timeout`: the same time drives the
// ring around the ×, and two owners of one deadline would drift apart. Hover HOLDS the countdown —
// otherwise the message vanishes from under the pointer that was reaching to close it.
//
// ⚠️ The remainder is computed from a TIMESTAMP, not by subtracting the step: in a background tab
// the browser throttles timers to one tick per second, and subtraction would stretch five seconds
// into fifty, blocking the queue.

const icons: Record<ToastLevel, Icon> = {
  success: IconCheck,
  info: IconInfoCircle,
  warn: IconAlertTriangle,
  error: IconAlertCircle,
}

/** Countdown step: the ring must melt smoothly, not jump once a second. */
const TICK_MS = 100

// Show the oldest: later arrivals wait their turn rather than covering it.
const current = computed(() => toasts.value[0] ?? null)

const left = ref(0)
// Two DIFFERENT things: `paused` — the pointer anywhere on the message (text is being read, hold the
// deadline); `overClose` — pointer or focus on the button itself (there the ring yields to the ×).
const paused = ref(false)
const overClose = ref(false)
let ticker: ReturnType<typeof setInterval> | undefined
let deadlineAt = 0

/** Whole seconds in the ring: 5-4-3-2-1. */
const seconds = computed(() => Math.ceil(left.value / 1000))
const percent = computed(() => {
  const total = current.value?.timeout ?? 0

  return total > 0 ? (left.value / total) * 100 : 0
})

// A message without a deadline (`timeout: 0`) stays until closed — the ring has nothing to show there.
const counting = computed(() => left.value > 0)

function stopTicker(): void {
  if (ticker !== undefined) {
    clearInterval(ticker)
    ticker = undefined
  }
}

watch(current, (toast) => {
  stopTicker()
  paused.value = false
  overClose.value = false
  left.value = toast?.timeout ?? 0

  if (toast === null || toast.timeout <= 0) {
    return
  }

  deadlineAt = Date.now() + toast.timeout

  ticker = setInterval(() => {
    // A pause pushes the deadline forward by exactly the elapsed time rather than "freezing" the counter.
    if (paused.value) {
      deadlineAt = Date.now() + left.value

      return
    }

    left.value = Math.max(0, deadlineAt - Date.now())

    if (left.value === 0) {
      stopTicker()
      dismissToast(toast.id)
    }
  }, TICK_MS)
}, { immediate: true })

onBeforeUnmount(stopTicker)

// Closed first, then run (see `ToastAction`).
function runAction(): void {
  const toast = current.value
  if (!toast?.action) {
    return
  }

  dismissToast(toast.id)
  void toast.action.run()
}
</script>

<template>
  <VSnackbar
    v-if="current"
    :key="current.id"
    :model-value="true"
    :timeout="-1"
    location="bottom right"
    class="toast"
    :class="`toast--${current.level}`"
  >
    <div
      class="toast__body"
      @mouseenter="paused = true"
      @mouseleave="paused = false"
    >
      <component :is="icons[current.level]" :size="18" class="toast__icon" />
      <span>{{ current.text }}</span>
    </div>

    <template #actions>
      <!-- An action ("Restore") sits before the close button, in the message tone — it answers
           the message. Hover holds the countdown here too: the toast must not vanish from under
           the pointer reaching for it. -->
      <button
        v-if="current.action"
        type="button"
        class="toast__action"
        @mouseenter="paused = true"
        @mouseleave="paused = false"
        @focus="paused = true"
        @blur="paused = false"
        @click="runAction"
      >
        {{ current.action.label }}
      </button>

      <!-- The button is ALWAYS there: it is both the keyboard focus target and the place for the
           countdown. Only its content changes — the ring at rest, the × under pointer and focus —
           so the layout doesn't move. -->
      <button
        type="button"
        class="toast__close"
        :aria-label="$t('common.action.close')"
        @mouseenter="paused = true; overClose = true"
        @mouseleave="paused = false; overClose = false"
        @focus="paused = true; overClose = true"
        @blur="paused = false; overClose = false"
        @click="dismissToast(current.id)"
      >
        <VProgressCircular
          v-if="counting && !overClose"
          :model-value="percent"
          :size="28"
          :width="2"
          class="toast__count"
        >
          {{ seconds }}
        </VProgressCircular>

        <IconX v-else :size="16" />
      </button>
    </template>
  </VSnackbar>
</template>

<style scoped>
.toast--success { --toast-accent: var(--success); --toast-bg: var(--success-soft); }
.toast--info    { --toast-accent: var(--info);    --toast-bg: var(--info-soft); }
.toast--warn    { --toast-accent: var(--warn);    --toast-bg: var(--warn-soft); }
.toast--error   { --toast-accent: var(--error);   --toast-bg: var(--error-soft); }

/* Vuetify draws the surface itself, so the tone goes on its wrapper. The text is plain, not in the
   tone color: a soft fill + a colored line give contrast below readable. */
.toast :deep(.v-snackbar__wrapper) {
  background: var(--toast-bg);
  color: var(--text);
  border: 1px solid color-mix(in srgb, var(--toast-accent) 32%, transparent);
  border-radius: var(--radius);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
}

.toast__body {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toast__icon {
  flex: none;
  color: var(--toast-accent);
}

.toast__count {
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* The ring is entirely in the message tone. Global rules in `styles/main.scss` paint ANY
   `v-progress-circular` with the accent and its track with `--border-soft`; the `.toast` prefix
   makes these selectors outweigh them. */
.toast :deep(.toast__count) {
  color: var(--toast-accent);
}
.toast :deep(.v-progress-circular__overlay) {
  stroke: var(--toast-accent);
}
.toast :deep(.v-progress-circular__underlay) {
  stroke: color-mix(in srgb, var(--toast-accent) 20%, transparent);
}

.toast__action {
  height: 28px;
  margin-right: 4px;
  padding: 0 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--toast-accent);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.15s ease;
}
.toast__action:hover {
  background: color-mix(in srgb, var(--toast-accent) 12%, transparent);
}
.toast__action:focus-visible {
  outline: 2px solid var(--toast-accent);
  outline-offset: 1px;
}

/* The button holds the size, not its content: the ring and the × swap within one 28×28 box,
   so the surface doesn't twitch. */
.toast__close {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text-muted);
  cursor: pointer;
}
.toast__close:hover {
  color: var(--toast-accent);
  background: color-mix(in srgb, var(--toast-accent) 12%, transparent);
}
.toast__close:focus-visible {
  outline: 2px solid var(--toast-accent);
  outline-offset: 1px;
}
</style>
