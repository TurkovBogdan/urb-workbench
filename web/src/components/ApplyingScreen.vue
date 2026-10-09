<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

defineProps<{
  /** The origin the server comes back at when its host/port changes; `null` — right here. */
  movingTo: string | null
}>()

const { t } = useI18n()

// Focus moves to the heading so a screen reader announces the change instead of staying on the
// Save button that is now hidden underneath.
const headingRef = ref<HTMLElement | null>(null)
onMounted(() => headingRef.value?.focus())
</script>

<template>
  <div class="applying-screen" role="alert" aria-live="polite" aria-busy="true">
    <div class="applying-screen__spinner" />
    <h1 ref="headingRef" tabindex="-1" class="applying-screen__title">
      {{ t('common.applying.title') }}
    </h1>
    <p v-if="movingTo" class="applying-screen__text">
      {{ t('common.applying.moving') }}
      <span class="applying-screen__address">{{ movingTo }}</span>
    </p>
    <p v-else class="applying-screen__text">{{ t('common.applying.description') }}</p>
  </div>
</template>

<style scoped>
/* Above every Vuetify layer, sidebar and overlays included: the layout is replaced, not dimmed. */
.applying-screen {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  text-align: center;
  background: var(--bg);
}

/* The boot splash's spinner, so the hand-off to it after the reload is seamless. */
.applying-screen__spinner {
  width: 44px;
  height: 44px;
  border: 4px solid color-mix(in srgb, var(--accent) 18%, transparent);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: applying-screen-spin 0.8s linear infinite;
}

@keyframes applying-screen-spin {
  to { transform: rotate(360deg); }
}

.applying-screen__title {
  margin: 28px 0 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
}

.applying-screen__title:focus {
  outline: none;
}

.applying-screen__text {
  margin: 8px 0 0;
  max-width: 420px;
  font-size: 14px;
  color: var(--text-muted);
}

.applying-screen__address {
  display: block;
  margin-top: 8px;
  font-family: var(--font-mono);
  color: var(--text);
}
</style>
