<script setup lang="ts">
// Modal window header: title, optional description, close × and the rule to the content — modelled
// on the payment form. The header owns the rule, not the content: a window can have several content
// blocks (checkout columns, tabs) but one header, and the rule must not depend on what's beneath it.
import { IconX } from '@tabler/icons-vue'
import { useI18n } from 'vue-i18n'

// The × is ALWAYS drawn and no prop turns it off: leaving a window is never optional, and for a
// blocking one it is the only exit. The parent must listen to `close`.
withDefaults(defineProps<{
  title: string
  /** Subtitle under the title. Without it the header is one line; the rule stays. */
  description?: string
  /** The rule to the content. Drop it only for a window WITHOUT a content block (`ConfirmDialog`). */
  rule?: boolean
  /** Work in progress: closing isn't allowed, but the × stays visible. */
  closeDisabled?: boolean
}>(), {
  description: undefined,
  rule: true,
  closeDisabled: false,
})

const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
</script>

<template>
  <header class="dlg-head" :class="{ 'dlg-head--rule': rule }">
    <!-- Title and description are exposed as slots: in the detail view the title is an editable
         field, and under it a button sits next to the code. Props remain the main path: a slot is
         for where a string stopped being a string, and a second header component isn't worth it. -->
    <div class="dlg-head__text">
      <slot name="title">
        <h2 class="dlg-head__title">{{ title }}</h2>
      </slot>
      <slot name="description">
        <p v-if="description" class="dlg-head__description">{{ description }}</p>
      </slot>
    </div>

    <!-- Actions sit to the RIGHT of the ×: leaving the window is a move toward its left edge, toward
         the content, while actions on the content itself continue the row outward. -->
    <div class="dlg-head__tools">
      <VBtn
        icon
        variant="text"
        :disabled="closeDisabled"
        :title="t('common.action.close')"
        @click="emit('close')"
      >
        <IconX :size="18" />
      </VBtn>

      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
/* Paddings and font size are taken from the payment form — it was the model. */
.dlg-head {
  /* The × is taller than the title line and, without a description, would grow the header by empty
     space. Both values are kept together: the button box is explicit, and negative margins of
     exactly the difference take it out of the height calculation. The × centers on the title line;
     the text sets the header height. */
  --dlg-close-size: 42px;
  --dlg-title-line: 24px;
  --dlg-pad-y: 22px;
  --dlg-pad-x: 24px;
  --dlg-close-shift: calc((var(--dlg-title-line) - var(--dlg-close-size)) / 2);

  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: var(--dlg-pad-y) var(--dlg-pad-x) 18px;
}

.dlg-head--rule { border-bottom: 1px solid var(--border-soft); }

/* The text half takes everything the action row leaves: it may hold a field, which would otherwise
   size to its own content. */
.dlg-head__text {
  flex: 1;
  min-width: 0;
}

.dlg-head__title {
  margin: 0;
  font-size: 18px;
  line-height: var(--dlg-title-line);
  font-weight: 700;
  color: var(--text);
}

.dlg-head__description { margin: 4px 0 0; font-size: 13px; color: var(--text-muted); }

/* The ROW holds the negative margins, not the ×: it may contain any number of actions, and the whole
   row is taken out of the header height calculation. */
.dlg-head__tools {
  display: flex;
  align-items: center;
  flex: none;
  margin-block: var(--dlg-close-shift);
  /* Right by just enough that the outermost button's edge sits as far from the right edge as from
     the top: vertically the row is already shifted by --dlg-close-shift. */
  margin-right: calc(var(--dlg-pad-y) + var(--dlg-close-shift) - var(--dlg-pad-x));
}

/* The box is explicit: for an icon button it depends on `density`, and here the whole row's shift
   depends on it. Slotted actions get it via the same rule — the row must stand on one axis. */
.dlg-head__tools :deep(.v-btn) {
  width: var(--dlg-close-size);
  height: var(--dlg-close-size);
}
</style>
