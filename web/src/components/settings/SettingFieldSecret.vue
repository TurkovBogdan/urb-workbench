<script setup lang="ts">
import type { StrFieldDescriptor } from '@/shared/settings-fields'

// The secret is never sent out: the backend sends the sentinel `NOT_CHANGED` (token set)
// or `""` (not set). The field holds the received value as is — masked
// (non-empty if set). Left untouched → goes back as the same sentinel, and the backend
// (src/core/_settings/api.py) does NOT update the token. A new value entered → it is saved.
defineProps<{
  field: StrFieldDescriptor
  modelValue: string
  error: string | null
  saving: boolean
}>()

defineEmits<{ 'update:modelValue': [string] }>()
</script>

<template>
  <VTextField
    :model-value="modelValue"
    type="password"
    autocomplete="off"
    data-1p-ignore
    data-lpignore="true"
    :label="field.label"
    :error-messages="error ?? undefined"
    hide-details="auto"
    :loading="saving"
    variant="outlined"
    density="comfortable"
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>
