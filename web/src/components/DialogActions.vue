<script setup lang="ts">
// The modal window's button bar. A separate component rather than `VCardActions`: that one hands all
// nested buttons `slim: true` and `variant: 'text'` via provideDefaults, so the primary action loses
// its fill and height, and `color` stops working. Here buttons are ordinary.
</script>

<template>
  <div class="dlg-actions">
    <slot />
  </div>
</template>

<style scoped>
/* The bottom mirrors the header's top, the sides are the window's shared 24px. At least 12px on top:
   content with its own scrolling is clipped at the edge, and without it the buttons would butt
   against the clipped text. */
.dlg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 24px 22px;
}
</style>
