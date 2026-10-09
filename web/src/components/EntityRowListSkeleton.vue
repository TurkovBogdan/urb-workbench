<script setup lang="ts">
// The placeholder of `EntityRowList` while it loads: the same row box, gap and icon badge, so
// nothing jumps when the real rows arrive. Vuetify's `list-item-avatar-two-line` brings its own
// 64px bone and 40px avatar; both are fitted to the row here, not in every page that waits.
withDefaults(defineProps<{ rows?: number }>(), { rows: 3 })
</script>

<template>
  <div class="entity-skel-list">
    <VCard v-for="n in rows" :key="n" variant="flat" class="entity-skel-row">
      <VSkeletonLoader type="list-item-avatar-two-line" />
    </VCard>
  </div>
</template>

<style scoped>
.entity-skel-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* The box of `.entity-row`: the same padding, and the 38px text block as the content height. */
.entity-skel-row { padding: 14px 16px; }

.entity-skel-row :deep(.v-skeleton-loader) {
  width: 100%;
  padding: 0;
  background: transparent;
}

.entity-skel-row :deep(.v-skeleton-loader__list-item-avatar-two-line) {
  height: 38px;
  padding: 0;
}

.entity-skel-row :deep(.v-skeleton-loader__avatar) {
  width: 34px;
  min-width: 34px;
  height: 34px;
  min-height: 34px;
  max-height: 34px;
  margin: 0 16px 0 0;
  border-radius: 8px;
}

/* Vuetify spaces its two text bones with 16px margins, which makes a 64px block that overflows the
   row and pushes the avatar off centre; here they sit like the title and description. */
.entity-skel-row :deep(.v-skeleton-loader__sentences) {
  height: 38px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 8px;
}

/* Vuetify grows a text bone with `flex: 1 1 100%` — along a column that is height, not width. */
.entity-skel-row :deep(.v-skeleton-loader__text) {
  flex: none;
  height: 12px;
  margin: 0;
}
</style>
