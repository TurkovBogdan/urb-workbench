<script setup lang="ts">
// A keyboard key as the interface names it — one for the whole app.
//
// One on purpose: a key is how a shortcut is learned from the screen rather than from the code,
// and it should read the same next to a menu item, in the editor's slash menu, anywhere. The face
// is monospaced so a digit and a letter take the same width and a row of keys lines up; it stays
// quieter than the label it sits by — a hint, not a button.
defineProps<{
  /** What is written on the key: `1`, `Ctrl`, `↵`. */
  label: string
}>()
</script>

<template>
  <kbd class="key-cap">{{ label }}</kbd>
</template>

<style scoped>
.key-cap {
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1;
  color: var(--text-faint);
  background: color-mix(in srgb, rgb(var(--v-theme-on-surface)) 6%, transparent);
  border: 1px solid var(--border-soft);
  border-radius: 3px;
  padding: 2px 4px;
  min-width: 16px;
  text-align: center;
}
</style>
