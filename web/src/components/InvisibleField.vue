<script setup lang="ts">
// An invisible text field: it reads as plain text in every state — no border, no background, not
// at rest, not under the cursor, not on focus. What gives it away is the text cursor over it and
// the caret inside it. For a value edited right where it is read, such as a page title: any chrome
// would turn the heading into a form.
//
// The text starts right at the field's edge, with no padding: it stands on the same line as the
// text around it. Size and weight of the text belong to the place that uses the field — the field
// only removes its chrome.
//
// Attributes and slots pass through to VTextField as is.
import { useSlots } from 'vue'

const model = defineModel<string>({ default: '' })

const slots = useSlots()
</script>

<template>
  <VTextField v-model="model" variant="plain" hide-details class="invisible-field">
    <template v-for="(_, name) in slots" #[name]="scope">
      <slot :name="name" v-bind="scope ?? {}" />
    </template>
  </VTextField>
</template>

<style scoped>
.invisible-field :deep(.v-field),
.invisible-field :deep(.v-field:hover),
.invisible-field :deep(.v-field--focused) {
  padding-inline: 0;
  background: transparent;
  box-shadow: none;
  cursor: text;
}

.invisible-field :deep(.v-field__overlay),
.invisible-field :deep(.v-field__outline) { display: none; }
</style>
