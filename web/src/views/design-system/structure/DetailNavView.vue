<script setup lang="ts">
// The detail page standard: a sticky navigation column on the left, content on the right, no header.
// The rule is checked automatically (tests/apps/test_web_page_header.py), so here it isn't retold
// in prose but shown as a live panel in both its forms — with its own page action and without one.
import { useI18n } from 'vue-i18n'
import { IconFolderPlus } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import DetailNav from '@/layout/components/DetailNav.vue'
import DetailHead from '@/layout/components/DetailHead.vue'
import CodeBlock from '@/components/CodeBlock.vue'

const { t } = useI18n()

const SAMPLE_CODE = 'RESEARCH@bc854947af58733bd93c3d'

// The page doesn't draw the column — it fills it: the frame (`DetailShell`) sits on the parent route
// and survives moving from one artifact to another.
const snippet = `// routes.ts — detail pages are children of the shared shell
{
  path: '/research',
  component: () => import('@/layout/templates/DetailShell.vue'),
  children: [
    { path: 'researches/:code', name: 'research-detail', component: … },
    { path: 'areas/:code',      name: 'research-area',   component: … },
  ],
}

// ResearchView.vue
useDetailRail(() => ({
  parent: PARENT_PATH,
  label: t('research.back.researches'),
  code: store.research?.code ?? '',
  appearance: true,
  sections: navSections.value,
  search: {
    label: t('research.research.detail.search'),
    value: store.search,
    update: (query) => { store.search = query },
    summary: store.searching ? t('research.research.detail.found', { n: store.matchCount }) : '',
  },
}))`

const templateSnippet = `<template>
  <div>
    <SectionError v-if="store.error" :error="store.error" />

    <!-- The artifact's name belongs to the artifact, so it sits above the content, not in the rail.
         Actions sit at the right edge of the same row, in the same place on every detail page. -->
    <DetailHead :code="store.research.code" :loading="store.loading" @refresh="reload">
      <template #above><GroupLink v-bind="shelf" /></template>
      <TitleEditor variant="title" :heading="1" :title="store.research.title" … />
    </DetailHead>

    <VCard variant="outlined" rounded="lg">…</VCard>
  </div>
</template>`

// The address is ONE LEVEL up, not the section root: for a source that is the zone, not the
// research and not the registry. It is a fallback — normally the button goes back through history,
// and the address is reached only when the page was entered via a direct link.
const parentSnippet = `const parentPath = computed(() =>
  source.value ? \`/research/areas/\${source.value.area_code}\` : '/research/researches',
)`

const SAMPLE_PARENT = '/design-system/detail-nav'
</script>

<template>
  <PageLayout>
    <div class="ds-page">
      <PageHeader
        :title="t('design-system.page.detail-nav.title')"
        :description="t('design-system.page.detail-nav.description')"
        back-to="/design-system"
      />

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.detail-nav.rule') }}</h6>
        <p class="ds-note">{{ t('design-system.section.detail-nav.rule_note') }}</p>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.detail-nav.panel') }}</h6>
        <p class="ds-note">{{ t('design-system.section.detail-nav.panel_note') }}</p>
        <div class="ds-frame ds-rail">
          <DetailNav
            :parent="SAMPLE_PARENT"
            :label="t('design-system.section.detail-nav.sample.exit')"
            :code="SAMPLE_CODE"
            appearance
          />
        </div>
        <CodeBlock :code="parentSnippet" lang="ts" />
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.detail-nav.head') }}</h6>
        <p class="ds-note">{{ t('design-system.section.detail-nav.head_note') }}</p>
        <div class="ds-frame">
          <DetailHead :code="SAMPLE_CODE">
            <template #more>
              <VListItem :prepend-icon="IconFolderPlus">
                <VListItemTitle>
                  {{ t('design-system.section.detail-nav.sample.move_group') }}
                </VListItemTitle>
              </VListItem>
            </template>
            <template #above>
              <span class="ds-shelf">{{ t('design-system.section.detail-nav.sample.shelf') }}</span>
            </template>
            <h1 class="ds-title">{{ t('design-system.section.detail-nav.sample.title') }}</h1>
          </DetailHead>
        </div>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.detail-nav.parts') }}</h6>
        <div class="ds-card">
          <div class="ds-row">
            <span class="ds-tag">DetailLayout</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.layout') }}</p>
            <span class="ds-spec">320px + minmax(0, 1fr)</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">back</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.back') }}</p>
            <span class="ds-spec">history → parent</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">appearance</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.appearance') }}</p>
            <span class="ds-spec">card under the panel</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">parent</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.parent') }}</p>
            <span class="ds-spec">one level up</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">code</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.code') }}</p>
            <span class="ds-spec">head + rail</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">DetailHead</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.head') }}</p>
            <span class="ds-spec">label above cards</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">refresh</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.refresh') }}</p>
            <span class="ds-spec">right edge of the first row</span>
          </div>
          <div class="ds-row">
            <span class="ds-tag">more</span>
            <p class="ds-part">{{ t('design-system.section.detail-nav.part.more') }}</p>
            <span class="ds-spec">slot, otherwise no button</span>
          </div>
        </div>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.detail-nav.markup') }}</h6>
        <CodeBlock :code="snippet" lang="ts" />
        <CodeBlock :code="templateSnippet" lang="vue" />
      </section>
    </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 1100px; }
.ds-section { margin-bottom: 28px; }

/* The column lives on the page canvas, so in the demo it needs an outlined area, not a card.
   The width in the area is the one from the standard: at full width the labels don't wrap, and
   you can't see how the card actually behaves. */
.ds-frame {
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 12px;
}

.ds-rail {
  max-width: 320px;
}

.ds-card {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}

.ds-row {
  display: grid;
  grid-template-columns: 120px 1fr 220px;
  align-items: start;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-soft);
}
.ds-row:last-child { border-bottom: none; }

.ds-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
}

.ds-spec {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: right;
}

.ds-part {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}

.ds-note {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 12px;
  max-width: 720px;
}

.ds-shelf {
  font-size: 12px;
  color: var(--text-muted);
}

.ds-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
</style>
