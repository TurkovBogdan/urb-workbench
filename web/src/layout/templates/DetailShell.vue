<script setup lang="ts">
// The frame shared by all detail pages: a navigation rail on the left, the content on the right.
//
// It sits on the parent route, so going from a research to its zone doesn't rebuild the whole
// page — only the right half slides out and in, while the rail stays in place and rebuilds itself:
// the exit label, search and table of contents come from the registry (`detailRail`) filled by the
// incoming page. Each view used to render the rail itself, and on every transition it vanished
// along with the content — even though it showed almost the same thing.
//
// Scrolling and spacing still belong to `PageLayout`; `nested` tells it that an address change
// inside this frame is the start of a new page, not a move to another frame.
import { IconSearch } from '@tabler/icons-vue'

import PageLayout from './PageLayout.vue'
import DetailLayout from './DetailLayout.vue'
import DetailNav from '../components/DetailNav.vue'
import SectionNav from '@/components/SectionNav.vue'
import { detailRail } from '../detailRail'
import { endRouteTransition } from '@/composables/useRouteTransition'

const rail = detailRail()
</script>

<template>
  <PageLayout nested>
    <DetailLayout>
      <template #rail>
        <template v-if="rail">
          <DetailNav
            :parent="rail.parent"
            :label="rail.label"
            :code="rail.code"
            :appearance="rail.appearance"
          >
            <template v-if="rail.search">
              <VTextField
                :model-value="rail.search.value"
                :label="rail.search.label"
                :prepend-inner-icon="IconSearch"
                variant="outlined"
                density="comfortable"
                hide-details
                clearable
                @update:model-value="rail.search.update($event ?? '')"
              />
              <p v-if="rail.search.summary" class="rail-search__summary">
                {{ rail.search.summary }}
                <span v-if="rail.search.pending" class="rail-search__pending">
                  <VProgressCircular indeterminate size="11" width="2" />
                  {{ rail.search.pending }}
                </span>
              </p>
            </template>
          </DetailNav>

          <!-- Not every page has a table of contents, and it arrives with the page's data, so it
               also appears and leaves with motion: a flashing panel would read as a glitch. -->
          <Transition name="rail-card" mode="out-in">
            <SectionNav v-if="rail.sections?.length" :sections="rail.sections" />
          </Transition>
        </template>
      </template>

      <!-- The same transition as a full page change, but over the content only: the rail is
           outside it and doesn't flicker. The end of the enter is cleared right here — the top
           `Transition` in `App.vue` doesn't run for a move between nested addresses, and heavy
           content waits precisely for it. -->
      <RouterView v-slot="{ Component }">
        <Transition
          name="page"
          mode="out-in"
          @after-enter="endRouteTransition"
          @enter-cancelled="endRouteTransition"
        >
          <KeepAlive>
            <component :is="Component" />
          </KeepAlive>
        </Transition>
      </RouterView>
    </DetailLayout>
  </PageLayout>
</template>

<style scoped>
.rail-search__summary {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

/* The table-of-contents panel fades out while collapsing: the height animates via
   `interpolate-size` (auto ↔ 0), and `min-height: 0` is needed for an item of the flex rail to be
   able to shrink below its content at all. */
.rail-card-enter-active,
.rail-card-leave-active {
  overflow: hidden;
  min-height: 0;
  interpolate-size: allow-keywords;
  transition: opacity 0.18s ease, height 0.18s ease;
}

.rail-card-enter-from,
.rail-card-leave-to {
  opacity: 0;
  height: 0;
}

@media (prefers-reduced-motion: reduce) {
  .rail-card-enter-active,
  .rail-card-leave-active {
    transition: none;
  }
}

/* The catching-up half of the search: inline next to the counter rather than a place of its own —
   it refines exactly that number. */
.rail-search__pending {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: 6px;
  color: var(--text-faint);
}
</style>
