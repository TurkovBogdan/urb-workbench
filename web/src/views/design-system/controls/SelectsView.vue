<script setup lang="ts">
import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import VSelectSearch from '@/components/VSelectSearch.vue'
import VSelectStepper from '@/components/VSelectStepper.vue'
import {
  IconSearch,
  IconMapPin,
  IconUser,
  IconSortAscending,
  IconSortDescending,
  IconTable,
  IconLayoutGrid,
  IconFolders,
  IconServer,
  IconCoin,
  IconMessage,
} from '@tabler/icons-vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const items   = ['Moscow', 'Saint Petersburg', 'Kazan', 'Novosibirsk', 'Yekaterinburg']
const objects = [
  { title: 'Manager', value: 'manager' },
  { title: 'Developer', value: 'developer' },
  { title: 'Designer', value: 'designer' },
  { title: 'Analyst', value: 'analyst' },
]

const v1 = ref<string | null>(null)
const v2 = ref<string | null>(null)
const v3 = ref<string | null>(null)
const v4 = ref<string | null>(null)
const v5 = ref<string | null>(null)
const v6 = ref<string | null>(null)
const v7 = ref<string | null>(null)
const v8 = ref<string | null>(null)
const v9 = ref<string[]>([])
const v10 = ref<string | null>(null)

// Search-inside-dropdown demo. The pattern lives in the reusable VSelectSearch
// component (drop-in for VSelect); the page only wires items + v-model.
const cities = [
  'Moscow', 'Saint Petersburg', 'Novosibirsk', 'Yekaterinburg', 'Kazan',
  'Nizhny Novgorod', 'Chelyabinsk', 'Samara', 'Omsk', 'Rostov-on-Don',
  'Ufa', 'Krasnoyarsk', 'Voronezh', 'Perm', 'Volgograd',
]
const v11 = ref<string | null>(null)

const searchSnippet = `<script setup lang="ts">
import VSelectSearch from '@/components/VSelectSearch.vue'
import { ref } from 'vue'

const cities = ['Moscow', 'Saint Petersburg', 'Novosibirsk', /* … */]
const value = ref<string | null>(null)
<\/script>

<template>
  <VSelectSearch
    v-model="value"
    :items="cities"
    label="City"
    variant="outlined"
  />
</template>`

// Иконки в пунктах. Штатный путь — `props.prependIcon` у самого пункта; своя разметка (плашка
// в цвете, две строки, счётчик) — слоты `#item` / `#selection`.
const viewOptions = [
  { title: 'Table', value: 'table', props: { prependIcon: IconTable } },
  { title: 'Cards', value: 'cards', props: { prependIcon: IconLayoutGrid } },
  { title: 'Cards by group', value: 'grouped', props: { prependIcon: IconFolders } },
]
const viewValue = ref('table')

const shelfOptions = [
  { title: 'DevOps: server setup', value: 'devops', icon: IconServer, tone: '#0994BA' },
  { title: 'Finance, tax and law', value: 'finance', icon: IconCoin, tone: '#928A07' },
  { title: 'Team communications', value: 'chat', icon: IconMessage, tone: '#A35DE4' },
]
const shelfValue = ref('devops')

const iconsSnippet = `<template>
  <!-- The standard way: the item carries its own icon -->
  <VSelect :items="[{ title: 'Table', value: 'table', props: { prependIcon: IconTable } }]" />

  <!-- Custom markup for the item and the selected value.
       :chips="false" is required: with chips (the global default) Vuetify renders #chip
       and silently ignores #selection. The slot receives the ORIGINAL item object — not item.raw. -->
  <VSelect :items="shelves" :chips="false">
    <template #item="{ props: itemProps, item }">
      <VListItem v-bind="itemProps">
        <template #prepend><ShelfSwatch :icon="item.icon" :tone="item.tone" /></template>
      </VListItem>
    </template>
    <template #selection="{ item }">
      <ShelfSwatch :icon="item.icon" :tone="item.tone" /> {{ item.title }}
    </template>
  </VSelect>
</template>`

// Селект с приросшей кнопкой — на примере сортировки: поле выбирает, по чему сортировать,
// кнопка переключает направление, и порознь они не читаются.
const sortFields = ['Date created', 'Date updated', 'Name']
const sortBy = ref(sortFields[0])
const sortDir = ref<'asc' | 'desc'>('desc')
const sortBy2 = ref(sortFields[0])
const sortDir2 = ref<'asc' | 'desc'>('desc')

// Классы глобальные (main.scss) — своего CSS месту применения не нужно.
const groupSnippet = `<template>
  <div class="field-group">
    <VSelect v-model="sortBy" :items="fields" label="Sort by"
      variant="outlined" density="comfortable" hide-details />
    <VBtn variant="outlined" density="comfortable" icon class="field-group__btn"
      :aria-label="label" @click="toggleDir">
      <IconSortAscending v-if="dir === 'asc'" :size="16" />
      <IconSortDescending v-else :size="16" />
    </VBtn>
  </div>
</template>`

// Селект с шагом — на примере кегля: варианты стоят лестницей, и соседний перебирают подряд,
// сравнивая результат на глаз.
const sizeOptions = [14, 15, 16, 17, 18, 20].map((size) => ({ title: `${size} px`, value: size }))
const stepSize = ref(16)
const stepShelf = ref('devops')

const stepperSnippet = `<script setup lang="ts">
import VSelectStepper from '@/components/VSelectStepper.vue'
import { ref } from 'vue'

const sizes = [14, 15, 16, 17, 18, 20].map(s => ({ title: \`\${s} px\`, value: s }))
const size = ref(16)
<\/script>

<template>
  <VSelectStepper
    v-model="size"
    :items="sizes"
    label="Text size"
    variant="outlined"
    density="comfortable"
    hide-details
  />
</template>`

const { t } = useI18n()
</script>

<template>
  <PageLayout>
  <div class="ds-page">
    <PageHeader :title="t('design-system.page.selects.title')" :description="t('design-system.page.selects.description')" back-to="/design-system" />

    <!-- Variants -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.variants') }}</h6>
      <div class="ds-card">

        <div class="ds-row">
          <span class="ds-tag">outlined</span>
          <div class="ds-controls">
            <VSelect v-model="v1" :items="items" label="City" variant="outlined" hide-details />
          </div>
          <span class="ds-spec">primary</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">filled</span>
          <div class="ds-controls">
            <VSelect v-model="v2" :items="items" label="City" variant="filled" hide-details />
          </div>
          <span class="ds-spec">with background</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">plain</span>
          <div class="ds-controls">
            <VSelect v-model="v3" :items="items" placeholder="City" variant="plain" hide-details />
          </div>
          <span class="ds-spec">no border · label not used</span>
        </div>

      </div>
    </section>

    <!-- States -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.states') }}</h6>
      <div class="ds-card">

        <div class="ds-row">
          <span class="ds-tag">clearable</span>
          <div class="ds-controls">
            <VSelect v-model="v4" :items="items" label="City" variant="outlined" clearable hide-details />
          </div>
          <span class="ds-spec">clearable</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">loading</span>
          <div class="ds-controls">
            <VSelect v-model="v5" :items="items" label="City" variant="outlined" loading hide-details />
          </div>
          <span class="ds-spec">loading</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">disabled</span>
          <div class="ds-controls">
            <VSelect :items="items" label="City" variant="outlined" model-value="Moscow" disabled hide-details />
          </div>
          <span class="ds-spec">disabled</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">error</span>
          <div class="ds-controls">
            <VSelect :items="items" label="City" variant="outlined" :error-messages="['This field is required']" />
          </div>
          <span class="ds-spec">:error-messages</span>
        </div>

      </div>
    </section>

    <!-- With icons -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.withIcons') }}</h6>
      <div class="ds-card">

        <div class="ds-row">
          <span class="ds-tag">prepend-inner</span>
          <div class="ds-controls">
            <VSelect v-model="v6" :items="items" label="City" variant="outlined"
              :prepend-inner-icon="IconMapPin" hide-details />
          </div>
          <span class="ds-spec">:prepend-inner-icon</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">prepend</span>
          <div class="ds-controls">
            <VSelect v-model="v7" :items="items" label="City" variant="outlined"
              :prepend-icon="IconUser" hide-details />
          </div>
          <span class="ds-spec">:prepend-icon</span>
        </div>

      </div>
    </section>

    <!-- Objects -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.objects') }}</h6>
      <div class="ds-card">

        <div class="ds-row">
          <span class="ds-tag">items objects</span>
          <div class="ds-controls">
            <VSelect v-model="v8" :items="objects" item-title="title" item-value="value"
              label="Position" variant="outlined" hide-details />
          </div>
          <span class="ds-spec">item-title / item-value</span>
        </div>

        <div class="ds-row">
          <span class="ds-tag">multiple</span>
          <div class="ds-controls">
            <VSelect v-model="v9" :items="items" label="Cities" variant="outlined" multiple hide-details />
          </div>
          <span class="ds-spec">chips by default</span>
        </div>

      </div>

      <p class="ds-note">
        Chips for multiselects are on globally (chips / closable-chips in Vuetify
        defaults) — a plain <code>multiple</code> already renders the selection as chips in
        the design system's style. A single selection stays plain text. Need a compact
        view (a "+N" count via the <code>#selection</code> slot) — turn chips off
        with the <code>:chips="false"</code> prop.
      </p>
    </section>

    <!-- VAutocomplete -->
    <section class="ds-section">
      <h6 class="mb-3">Autocomplete</h6>
      <div class="ds-card">

        <div class="ds-row">
          <span class="ds-tag">autocomplete</span>
          <div class="ds-controls">
            <VAutocomplete v-model="v10" :items="items" label="Search city" variant="outlined"
              :prepend-inner-icon="IconSearch" clearable hide-details />
          </div>
          <span class="ds-spec">VAutocomplete</span>
        </div>

      </div>
    </section>

    <!-- Search inside dropdown -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.searchInDropdown') }}</h6>
      <div class="ds-card">

        <div class="ds-row">
          <span class="ds-tag">VSelectSearch</span>
          <div class="ds-controls">
            <VSelectSearch v-model="v11" :items="cities" label="City" variant="outlined" hide-details />
          </div>
          <span class="ds-spec">drop-in for VSelect</span>
        </div>

      </div>

      <p class="ds-note">
        VSelectSearch — a drop-in wrapper over VSelect that pins a search row atop the open
        menu (#prepend-item) and filters items in place. VAutocomplete merges the query into
        the field; this keeps the field display intact. Props/slots pass through to VSelect.
      </p>

      <CodeBlock :code="searchSnippet" lang="vue" variant="icon" class="mt-3" />
    </section>

    <!-- Icons inside items -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.itemIcons') }}</h6>
      <div class="ds-card">

        <div class="ds-row ds-row--center">
          <span class="ds-tag">prependIcon</span>
          <div class="ds-controls">
            <VSelect
              v-model="viewValue"
              :items="viewOptions"
              label="Research list"
              variant="outlined"
              density="comfortable"
              hide-details
            />
          </div>
          <span class="ds-spec">props.prependIcon on the item</span>
        </div>

        <div class="ds-row ds-row--center">
          <span class="ds-tag">#item · #selection</span>
          <div class="ds-controls">
            <VSelect
              v-model="shelfValue"
              :items="shelfOptions"
              :chips="false"
              label="Shelf"
              variant="outlined"
              density="comfortable"
              hide-details
            >
              <template #item="{ props: itemProps, item }">
                <VListItem v-bind="itemProps">
                  <template #prepend>
                    <span class="swatch" :style="{ '--tone': item.tone }">
                      <component :is="item.icon" :size="14" :stroke-width="1.7" />
                    </span>
                  </template>
                </VListItem>
              </template>

              <template #selection="{ item }">
                <span class="swatch-line">
                  <span class="swatch" :style="{ '--tone': item.tone }">
                    <component :is="item.icon" :size="14" :stroke-width="1.7" />
                  </span>
                  {{ item.title }}
                </span>
              </template>
            </VSelect>
          </div>
          <span class="ds-spec">custom badge · :chips="false"</span>
        </div>

      </div>

      <p class="ds-note">
        The gap between icon and label is normalized globally: Vuetify keeps
        <code>--v-list-prepend-gap</code> at 32px — room for an avatar, which dropdown
        lists never have — and at that width an icon with a label reads as two unrelated
        columns. In <code>main.scss</code> the gap for lists inside menus and selects is set
        to 10px, so the call site needs no fixing up.
      </p>

      <p class="ds-note">
        Custom item markup is the <code>#item</code> slot, custom markup for the selected
        value is <code>#selection</code>. Two traps: the slot gets the <strong>raw</strong>
        item object (<code>item.tone</code>, not <code>item.raw.tone</code>), and
        <code>#selection</code> only works with <code>:chips="false"</code> — with chips
        (the global default) Vuetify renders <code>#chip</code> and silently ignores it.
      </p>

      <CodeBlock :code="iconsSnippet" lang="vue" variant="icon" class="mt-3" />
    </section>

    <!-- Select + attached button -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.withButton') }}</h6>
      <div class="ds-card">

        <div class="ds-row ds-row--center">
          <span class="ds-tag">comfortable</span>
          <div class="ds-controls">
            <div class="field-group">
              <VSelect
                v-model="sortBy"
                :items="sortFields"
                label="Sort by"
                variant="outlined"
                density="comfortable"
                hide-details
              />
              <VBtn
                variant="outlined"
                density="comfortable"
                icon
                class="field-group__btn"
                :aria-label="sortDir === 'asc' ? 'Ascending' : 'Descending'"
                @click="sortDir = sortDir === 'asc' ? 'desc' : 'asc'"
              >
                <IconSortAscending v-if="sortDir === 'asc'" :size="16" />
                <IconSortDescending v-else :size="16" />
              </VBtn>
            </div>
          </div>
          <span class="ds-spec">32px · page filters</span>
        </div>

        <div class="ds-row ds-row--center">
          <span class="ds-tag">default</span>
          <div class="ds-controls">
            <div class="field-group">
              <VSelect
                v-model="sortBy2"
                :items="sortFields"
                label="Sort by"
                variant="outlined"
                hide-details
              />
              <VBtn
                variant="outlined"
                icon
                class="field-group__btn"
                :aria-label="sortDir2 === 'asc' ? 'Ascending' : 'Descending'"
                @click="sortDir2 = sortDir2 === 'asc' ? 'desc' : 'asc'"
              >
                <IconSortAscending v-if="sortDir2 === 'asc'" :size="18" />
                <IconSortDescending v-else :size="18" />
              </VBtn>
            </div>
          </div>
          <span class="ds-spec">36px · forms</span>
        </div>

      </div>

      <p class="ds-note">
        A field and a button that read as one control: sort direction is meaningless
        without the field it sorts by, and a separate button next to it looks like a
        standalone action. The fusion is done by markup, not the component: a pair of classes,
        <code>.field-group</code> / <code>.field-group__btn</code>, lives globally in
        <code>main.scss</code> — the field's right corner is squared off, the button's left
        one, and the button is shifted by a pixel so the border at the seam doesn't double up.
        The button's box follows its <code>density</code>: that prop only governs height, and
        Vuetify derives an icon button's side from it too, giving a rectangle without a width.
        This is how the sort filters are built in the research registry and the group list.
      </p>

      <CodeBlock :code="groupSnippet" lang="vue" variant="icon" class="mt-3" />
    </section>

    <!-- Select + prev/next steppers -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.withSteppers') }}</h6>
      <div class="ds-card">

        <div class="ds-row ds-row--center">
          <span class="ds-tag">default</span>
          <div class="ds-controls">
            <VSelectStepper
              class="ds-stepper"
              v-model="stepSize"
              :items="sizeOptions"
              label="Text size"
              variant="outlined"
              hide-details
            />
          </div>
          <span class="ds-spec">36px · value ladder</span>
        </div>

        <div class="ds-row ds-row--center">
          <span class="ds-tag">comfortable</span>
          <div class="ds-controls">
            <VSelectStepper
              class="ds-stepper"
              v-model="stepShelf"
              :items="shelfOptions"
              label="Shelf"
              variant="outlined"
              density="comfortable"
              hide-details
            />
          </div>
          <span class="ds-spec">32px · objects</span>
        </div>

      </div>

      <p class="ds-note">
        Steps to the neighboring option when item order is meaningful: font size, weight,
        line height, page size. Opening the list just to step one item over is three moves
        instead of one, but the list is still there: jumping to a far option with the buttons
        alone would take too long. Edges <strong>don't wrap</strong> — the left button dims
        on the first item, the right one on the last: otherwise a step click would slip past
        the edge of the set unnoticed. Nothing selected — stepping forward picks the first
        item, back picks the last.
      </p>

      <p class="ds-note">
        The fusion is the same pair of classes, <code>.field-group</code> /
        <code>.field-group__btn</code>, as for the button on the right, plus the
        <code>--before</code> modifier for the button on the left. The step logic lives in
        the <code>VSelectStepper</code> component (a wrapper over VSelect: <code>$attrs</code>
        and slots pass straight through), not at the call site — there's no reason to count
        the index and dim the edge buttons again in every screen. <code>density</code> is its
        own prop on it: the field and both buttons all keep it.
      </p>

      <CodeBlock :code="stepperSnippet" lang="vue" variant="icon" class="mt-3" />
    </section>

    <!-- Sizes (density axis) -->
    <section class="ds-section">
      <h6 class="mb-3">{{ t('design-system.section.selects.sizes') }}</h6>
      <div class="ds-card">

        <div class="ds-row ds-row--center">
          <span class="ds-tag">default</span>
          <div class="ds-controls">
            <VSelect :items="items" label="City" variant="outlined" hide-details />
          </div>
          <span class="ds-spec">density="default" · 36px</span>
        </div>

        <div class="ds-row ds-row--center">
          <span class="ds-tag">comfortable</span>
          <div class="ds-controls">
            <VSelect :items="items" label="City" variant="outlined" density="comfortable" hide-details />
          </div>
          <span class="ds-spec">density="comfortable" · 32px</span>
        </div>

        <div class="ds-row ds-row--center">
          <span class="ds-tag">compact</span>
          <div class="ds-controls">
            <VSelect :items="items" label="City" variant="outlined" density="compact" hide-details />
          </div>
          <span class="ds-spec">density="compact" · 28px</span>
        </div>

        <div class="ds-row ds-row--center">
          <span class="ds-tag">compact plain</span>
          <div class="ds-controls">
            <VSelect :items="items" placeholder="City" variant="plain" density="compact" hide-details />
          </div>
          <span class="ds-spec">inline / filters · 28px</span>
        </div>

      </div>

      <p class="ds-note">
        Field size is set by the <code>density</code> axis — the only native height
        mechanism Vuetify fields have (the <code>size</code> prop, unlike on buttons, is
        absent here). Heights are set globally in <code>main.scss</code> and are the same
        across all fields (selects, text, number, date): <code>default</code> 36px ·
        <code>comfortable</code> 32px · <code>compact</code> 28px. By Vuetify's semantics
        <code>default</code> is the tallest, and each step down shrinks height and vertical
        padding in sync.
      </p>
    </section>

  </div>
  </PageLayout>
</template>

<style scoped>
.ds-page { max-width: 860px; }

.ds-section { margin-bottom: 28px; }

.ds-card {
  background: var(--surface);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius);
  overflow: hidden;
}

.ds-row {
  display: grid;
  grid-template-columns: 100px 1fr 200px;
  align-items: start;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-soft);
  &:last-child { border-bottom: none; }
  &.ds-row--center { align-items: center; }
}

.ds-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-faint);
  padding-top: 10px;
}

.ds-spec {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: right;
  padding-top: 10px;
}

.ds-controls {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}

.v-select, .v-autocomplete {
  min-width: 220px;
  max-width: 280px;
}

/* У селекта с шагом ширину держит вся тройка: поле внутри компонента до правила выше не
   достаёт (чужая область видимости), а кнопки по краям должны стоять на её границах. */
.ds-stepper {
  width: 280px;
}

/* Плашка пункта: иконка в цвете сущности — так полка узнаётся в реестре исследований. */
.swatch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  flex: none;
  color: var(--tone);
  background: color-mix(in srgb, var(--tone) 14%, transparent);
}

.swatch-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.ds-note {
  margin-top: 14px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
}
</style>
