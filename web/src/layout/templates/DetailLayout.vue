<script setup lang="ts">
// Layout of a detail page: a sticky navigation rail on the left and the content on the right.
//
// A detail page needs no header of its own — the exit, the page's actions and the table of contents
// live in the rail and stay on screen along the whole document, while the artifact's name belongs
// to the document itself and opens its content as a caption above the cards. The standard
// `PageHeader` stays with lists, where the meaning is exactly the opposite: there the section name
// is the page title.
//
// The template nests inside `PageLayout` (which owns scrolling and spacing) and sets neither
// scrolling nor padding itself — only the two tracks.
</script>

<template>
  <div class="detail-layout">
    <div class="detail-layout__rail">
      <slot name="rail" />
    </div>

    <div class="detail-layout__main">
      <slot />
    </div>
  </div>
</template>

<style scoped>
/* The rail is sized in pixels, not in twelfths: it needs width for the label and the table of
   contents, and that need doesn't depend on screen width — on a wide monitor a fraction would give
   it extra room taken from the text. The content takes all the rest precisely via
   `minmax(0, 1fr)`: without the lower bound a table with long urls inflates its track and pushes
   the grid off screen. */
.detail-layout {
  --rail-width: 320px;

  display: grid;
  grid-template-columns: var(--rail-width) minmax(0, 1fr);
  gap: 0 24px;
  align-items: start;
}

/* The whole rail is sticky, not just the table of contents: if they came apart, its panels would
   drift half a screen away from each other. The spacing between panels belongs to the panels
   themselves (`margin-bottom`), not to the rail's `gap` — the rail outlives its parts appearing and
   leaving. */
.detail-layout__rail {
  min-width: 0;
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 96px);
}

.detail-layout__main {
  min-width: 0;
}

/* On a narrow screen a separate navigation track is no longer spare room but space taken from the
   text: the grid collapses into one, and both parts stack at full width. */
@media (max-width: 1099px) {
  .detail-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .detail-layout__rail {
    position: static;
    max-height: none;
    margin-bottom: 12px;
  }
}
</style>
