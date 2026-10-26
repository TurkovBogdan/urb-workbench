<script setup lang="ts">
// What the import will do without asking: codes that change whatever is chosen, paths that move,
// references out of the archive. An empty bucket is not shown — a heading with a zero would read as
// trouble found.
import { computed } from 'vue'

import Spoiler from '@/components/Spoiler.vue'

export interface TransferNoticeBucket {
  key: string
  title: string
  lines: string[]
}

const props = defineProps<{ buckets: TransferNoticeBucket[] }>()

const shown = computed(() => props.buckets.filter((bucket) => bucket.lines.length > 0))
</script>

<template>
  <div v-if="shown.length" class="transfer-notices">
    <Spoiler v-for="bucket in shown" :key="bucket.key" variant="minimal" :title="`${bucket.title} · ${bucket.lines.length}`">
      <ul class="transfer-notices__list">
        <li v-for="line in bucket.lines" :key="line">{{ line }}</li>
      </ul>
    </Spoiler>
  </div>
</template>

<style scoped>
.transfer-notices {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.transfer-notices__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0 0 6px;
  list-style: none;
  font-size: 12px;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
</style>
