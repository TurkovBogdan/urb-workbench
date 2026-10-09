<script setup lang="ts">
// Settings group card: a title, an explanation under it, then the fields.
//
// The anatomy is the same as the module card on /settings/modules (title → description → rule →
// fields in columns via the `.settings-columns` utility): settings groups read the same regardless
// of whether their value lives in the database or in this browser. The description here is a plain
// string, not markdown: client settings have their own text rather than one from the backend
// schema, so links in it have nowhere to come from.
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <VCard variant="outlined" rounded="lg">
    <VCardTitle class="text-h6">{{ title }}</VCardTitle>
    <p v-if="description" class="settings-group__desc">{{ description }}</p>
    <VDivider />
    <VCardText class="settings-columns">
      <slot />
    </VCardText>
  </VCard>
</template>

<style scoped>
.settings-group__desc {
  margin: 0;
  padding: 0 16px 16px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-muted);
}
</style>
