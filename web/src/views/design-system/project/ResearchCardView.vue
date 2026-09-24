<script setup lang="ts">
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import ResearchCard from '@/features/research/components/ResearchCard.vue'
import type { ResearchListRow } from '@/features/research/api'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const row = (over: Partial<ResearchListRow>): ResearchListRow => ({
  code: 'RESEARCH@ef8a7d2f258de68b188bda',
  title: 'PostgreSQL: secure configuration and full isolation of external connections',
  description:
    'How to shut production PostgreSQL off from the outside world and what to keep open: access, TLS, pg_hba, network.',
  group_code: 'GROUP@0632ba069422e69f3410bd',
  group_name: 'DevOps: server setup',
  group_icon: 'server',
  group_color: 'sky',
  area_count: 5,
  query_count: 5,
  document_count: 26,
  document_kept: 8,
  document_filtered: 15,
  document_error: 3,
  created_at: '2026-08-14 10:02:00',
  updated_at: '2026-08-27 23:14:00',
  ...over,
})

const filed = row({})
const ungrouped = row({ code: 'RESEARCH@1b464e08943f77787fbc11', group_code: null, group_name: '' })

const longTitle = row({
  code: 'RESEARCH@95870b6e72eb40e293c564',
  title:
    'Intercom Messenger: widget parameters (boot/update, email prefill, custom attributes, auth vs anonymous)',
  group_name: 'Team communications: chat platforms',
  group_icon: 'message',
  group_color: 'violet',
})

const bare = row({ code: 'RESEARCH@9095d573a3038110079356', description: '' })

const usageSnippet = `<script setup lang="ts">
import ResearchCard from '@/features/research/components/ResearchCard.vue'
<\/script>

<template>
  <ResearchCard
    :research="item"
    :group-filterable="true"
    @open="router.push(\`/research/researches/\${item.code}\`)"
    @rename="openRenameDialog(item)"
    @group="openGroupDialog(item)"
    @detach="detach(item)"
    @remove="openDeleteDialog(item)"
    @filter-group="filterByGroup"
  />

  <!-- Filed into groups: the section heading already names the group -->
  <ResearchCard :research="item" :with-group="false" @open="open(item)" />
<\/template>`
</script>

<template>
  <PageLayout>
    <div class="ds-page">
      <PageHeader
        :title="t('design-system.page.research-card.title')"
        :description="t('design-system.page.research-card.description')"
        back-to="/design-system"
      />

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.research-card.base') }}</h6>
        <div class="ds-host ds-grid">
          <ResearchCard :research="filed" group-filterable />
          <ResearchCard :research="ungrouped" group-filterable />
        </div>
        <p class="ds-note">
          The footer carries the group and the update date. Without a group, only the date
          remains — there's no "no group" chip; its absence is the answer.
        </p>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.research-card.group') }}</h6>
        <div class="ds-host ds-grid">
          <ResearchCard :research="filed" :with-group="false" />
          <ResearchCard :research="filed" />
        </div>
        <p class="ds-note">
          <code>with-group="false"</code> — the group chip is hidden: that's how the tile looks
          in a group layout, where the section heading already names the group. Hidden on the
          left, shown on the right, but <code>group-filterable</code> isn't set, so the chip is
          just a label: clicking it only sets the filter where the list isn't already narrowed by group.
        </p>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.research-card.edges') }}</h6>
        <div class="ds-host ds-grid">
          <ResearchCard :research="longTitle" group-filterable />
          <ResearchCard :research="bare" group-filterable />
        </div>
        <p class="ds-note">
          A long title wraps, the description is cut at 128 characters, and the footer is pinned
          to the bottom — tiles in a row end on the same line regardless of text length.
        </p>
      </section>

      <section class="ds-section">
        <h6 class="mb-3">{{ t('design-system.section.research-card.usage') }}</h6>
        <CodeBlock :code="usageSnippet" lang="vue" />
        <p class="ds-note">
          The tile only reports: where to navigate, what to reload and which dialogs to open is
          decided by the list. No handlers are set here, so the menu items do nothing.
        </p>
      </section>
    </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 860px; }
.ds-section { margin-bottom: 28px; }

.ds-host {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  padding: 16px;
}

/* Две колонки — минимум, на котором видно выравнивание подвалов у соседок по ряду. */
.ds-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.ds-note {
  margin: 8px 2px 0;
  font-size: 12px;
  color: var(--text-faint);
}

.ds-note code {
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
