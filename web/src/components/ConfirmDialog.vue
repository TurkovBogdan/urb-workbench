<script setup lang="ts">
// Confirmation before something irreversible. Generic on purpose: removals, revocations and
// transfers all deserve the same pause, and they should look identical when they ask for it.
//
// The dialog does NOT perform the action — it asks. The parent listens for `confirm`, runs the
// work, and closes by setting the model. That split is what lets the parent keep the dialog open
// on failure (with the error rendered where the user is looking) instead of it vanishing on click
// and leaving them to guess whether anything happened.
import { onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppDialog from './AppDialog.vue'

const open = defineModel<boolean>({ required: true })

const props = withDefaults(defineProps<{
  title: string
  /** Body text. Use the default slot instead when it needs markup. */
  text?: string
  /** Label of the confirming button; defaults to a neutral "Confirm". */
  confirmLabel?: string
  /** Label of the backing-out button, when "Cancel" would read as the action itself. */
  cancelLabel?: string
  /** `danger` paints the confirm button as destructive — the default for a removal. */
  tone?: 'danger' | 'primary'
  /** Work in flight: buttons lock and the dialog refuses to close behind the user's back. */
  loading?: boolean
  /**
   * Enter confirms, wherever focus is. Opt-in: right for a reversible step taken often, wrong for
   * an irreversible one, where a reflexive Enter must not finish the job.
   */
  enterConfirms?: boolean
}>(), {
  text: undefined,
  confirmLabel: undefined,
  cancelLabel: undefined,
  tone: 'danger',
  loading: false,
  enterConfirms: false,
})

const emit = defineEmits<{ (e: 'confirm'): void }>()

const { t } = useI18n()

// The keystroke that opened the dialog — Enter on a menu item — is still on its way up to `window`
// when the listener is attached, and would confirm the dialog it has just opened.
let openedAt = 0

function confirmOnEnter(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.repeat || event.isComposing || props.loading) return
  if (event.timeStamp <= openedAt) return
  // A focused control answers Enter itself: on "Cancel" it means cancel, not confirm.
  if ((event.target as Element | null)?.closest('button, a, input, textarea, select, [role="button"]')) return
  event.preventDefault()
  emit('confirm')
}

function stopListening() {
  window.removeEventListener('keydown', confirmOnEnter)
}

watch(open, (isOpen) => {
  if (isOpen && props.enterConfirms) {
    openedAt = performance.now()
    window.addEventListener('keydown', confirmOnEnter)
  } else {
    stopListening()
  }
}, { immediate: true })

onBeforeUnmount(stopListening)
</script>

<template>
  <!-- `rule=false`: the question text below IS the description, there's nothing to separate from the title. -->
  <AppDialog
    v-model="open"
    :title="title"
    size="narrow"
    :rule="false"
    :persistent="loading"
    :close-disabled="loading"
  >
    <div class="cfm__text">
      <slot>{{ text }}</slot>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="loading" @click="open = false">
        {{ cancelLabel ?? t('common.action.cancel') }}
      </VBtn>
      <VBtn
        :color="tone === 'danger' ? 'error' : 'primary'"
        variant="flat"
        :loading="loading"
        @click="emit('confirm')"
      >
        {{ confirmLabel ?? t('common.action.confirm') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
/* The window body brings the paddings; the text is responsible only for its own typesetting. */
.cfm__text {
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
</style>
