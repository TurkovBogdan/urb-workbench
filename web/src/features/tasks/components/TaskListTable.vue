<script setup lang="ts">
// Формат «Список»: строки задач, разбитые заголовками зон, подзадачи — ветками под родителем.
//
// Анатомия: карточка со строками и полосой постраничности. Панель поиска и фильтров стоит
// ОТДЕЛЬНОЙ карточкой над списком (собирает её страница): поиск и фильтры правят то, что список
// показывает, и принадлежат не ему, а экрану целиком.
//
// ВЕТКИ И ПЕРЕТАСКИВАНИЕ живут в `TaskRows` — по компоненту на карточку группы: sortable заводится
// на контейнер, а контейнеров столько же, сколько зон. Здесь остаётся карточка вокруг них.
//
// РАЗМЕТКА — НЕ ТАБЛИЦА. Колонок у списка больше нет: их шапка ничего не сообщала (сортировки по
// колонкам здесь нет), а сетка из восьми колонок заставляла каждое поле держать свою ширину и
// потому заполнять её хоть чем-нибудь — прочерком, словом, шильдиком. Сейчас строка читается
// слева направо как фраза: состояние, важность, название, служебные пометки. Три зоны, а не
// восемь ячеек, и метка, которой у задачи нет, просто отсутствует.
//
// ТИШЕ ЗАГОЛОВКА. В трекере строку ищут глазами по названию, всё остальное — пометки, и они
// обязаны быть тише текста. Отсюда правило на весь файл: цвет несут только состояние и
// срочность, остальное — глиф и приглушённые 12px. Цветных слов и тональных плашек в строке нет
// вовсе: шильдик со словом «В тестировании» читается наравне с заголовком и отбирает у него
// первый взгляд.
//
// Одна задача — одна строка ровно в 36px: в списке ищут сверху вниз, а разноэтажные строки
// приходится разглядывать. Поэтому ни описания, ни тела в строке нет — за ними открывают окно.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconPlus } from '@tabler/icons-vue'

import IconSwatch from '@/components/IconSwatch.vue'
import TablePaginationBar from '@/components/TablePaginationBar.vue'

import TaskRows from './TaskRows.vue'
import { useTasksStore } from '../stores/tasks.store'
import type { TaskListRow } from '../api'

const props = defineProps<{
  /** Код задачи, на которую уходили со списка: вернувшись, человек видит свою строку отмеченной. */
  openCode?: string | null
}>()

const emit = defineEmits<{
  /** Открыть задачу: наружу едет код, а не строка, — адрес окна собирается из него. */
  open: [code: string]
  create: []
  edit: [task: TaskListRow]
  addChild: [task: TaskListRow]
}>()

const { t } = useI18n()
const store = useTasksStore()

// Сколько задач у каждого родителя — считаем по уже полученному списку, а не спрашиваем бэк:
// в ответе лежат ВСЕ задачи пространства, и та же арифметика, что стоит за `has_children`, здесь
// бесплатна. Счёт один на весь список: у каждой карточки группы свой компонент строк, и
// пересчитывать одно и то же в каждом незачем.
const childCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const task of store.items) {
    if (!task.parent_code) continue
    counts.set(task.parent_code, (counts.get(task.parent_code) ?? 0) + 1)
  }
  return counts
})

const showEmpty = computed(() => !store.loading && store.total === 0)

/** Ветку переставили — перестановку ведёт стор: он же перечитывает список после ответа. */
async function move(payload: { code: string; after: string | null; group?: string | null }) {
  await store.reorder(payload.code, payload.after, payload.group)
}

function onPageChange(page: number) {
  store.page = page
}

function onPageSizeChange(size: number) {
  store.pageSize = size
  store.resetPage()
}
</script>

<template>
  <div class="task-list">
    <!-- Обновление уже показанного списка — полоса поверху: подменять строки спиннером значило бы
         убирать с экрана то, что человек в этот момент читает. -->
    <VProgressLinear v-if="store.loading && store.total > 0" indeterminate height="2" class="task-list__progress" />

    <VCard v-if="store.loading && !store.total" variant="outlined" rounded="lg">
      <div class="task-list__state">
        <VProgressCircular indeterminate size="24" width="3" />
      </div>
    </VCard>

    <!-- Пусто по двум разным причинам, и ответы у них разные: задач нет вовсе — зовём завести
         первую; фильтры ничего не нашли — предлагаем их снять. -->
    <VCard v-else-if="showEmpty" variant="outlined" rounded="lg">
      <div class="task-list__state">
        <template v-if="store.isFilteredOut">
          <p class="task-list__state-title">{{ t('tasks.task.list.nothing_found') }}</p>
          <VBtn variant="text" size="small" @click="store.clearFilters">
            {{ t('tasks.task.list.clear_filters') }}
          </VBtn>
        </template>
        <template v-else>
          <p class="task-list__state-title">{{ t('tasks.task.list.empty') }}</p>
          <p class="task-list__state-hint">{{ t('tasks.task.list.empty_hint') }}</p>
          <VBtn color="primary" variant="flat" size="small" @click="emit('create')">
            <template #prepend><IconPlus :size="16" /></template>
            {{ t('tasks.task.list.add') }}
          </VBtn>
        </template>
      </div>
    </VCard>

    <!-- Группа = карточка. Секции идут БЕЗ `v-else`: на пустой странице их просто нет (см. стор),
         и связывать их ветвлением с двумя состояниями означало бы держать один и тот же ответ в
         двух местах.
         Пустые карточки стоят внизу и приглушены: они здесь как цель переноса, а не как
         содержимое, — задачу перетаскивают в чужую группу, и группы, которой нет на экране,
         для жеста не существует. -->
    <VCard
      v-for="section in store.sections"
      :key="section.group?.code ?? 'no-group'"
      variant="outlined"
      rounded="lg"
      class="task-group"
      :class="{ 'task-group--empty': !section.tasks.length }"
    >
      <!-- Шапка группы — штатная анатомия карточки (`VCardItem`): знак в `#prepend`, имя
           заголовком, описание подзаголовком. Выравнивание знака с двумя строками текста и
           отступы держит она сама; своя разметка повторяла бы её приблизительно.
           Знак взят у карточки группы на её собственной странице: один и тот же предмет должен
           узнаваться в обоих списках. У «Без группы» знака нет — там нейтральная точка: это не
           тема наравне с остальными, а остаток неразложенного. -->
      <VCardItem class="task-group__head">
        <template #prepend>
          <IconSwatch
            v-if="section.group"
            :icon="section.group.icon"
            :color="section.group.color"
            :width="28"
          />
          <span v-else class="task-group__dot" />
        </template>

        <VCardTitle class="task-group__title">
          {{ section.group ? section.group.title : t('tasks.task.list.no_group') }}
          <span class="task-group__count">{{ section.tasks.length }}</span>
        </VCardTitle>
        <VCardSubtitle v-if="section.group?.description">{{ section.group.description }}</VCardSubtitle>
      </VCardItem>

      <VDivider />

      <TaskRows
        :section="section"
        :open-code="props.openCode"
        :child-counts="childCounts"
        @open="emit('open', $event)"
        @edit="emit('edit', $event)"
        @add-child="emit('addChild', $event)"
        @remove="store.remove($event)"
        @restore="store.restore($event)"
        @move="move"
      />
    </VCard>

    <!-- Полоса постраничности — общая на все карточки групп и потому стоит под ними, а не внутри
         какой-то одной: страницами бьётся весь список, а не отдельная группа. Показывается, только
         когда страниц больше одной: на списке из пяти задач «1–5 из 5» и выбор размера страницы —
         это подпись под тем, что и так целиком на экране. -->
    <VCard v-if="store.pageCount > 1" variant="outlined" rounded="lg">
      <TablePaginationBar
        :page="store.page"
        :page-size="store.pageSize"
        :total="store.total"
        :page-count="store.pageCount"
        @update:page="onPageChange"
        @update:page-size="onPageSizeChange"
      />
    </VCard>
  </div>
</template>

<style scoped>
/* ── Карточка группы ───────────────────────────────────────────────────────────
   Группа — своя карточка, а не заголовок посреди общего полотна: у неё есть имя, знак и то, о чём
   она, и всё это принадлежит её задачам, а не списку целиком. Зазор между карточками больше
   любого внутреннего: он и разделяет группы. */
.task-list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Полоса обновления лежит НАД карточками и не раздвигает их: встань она строкой в колонку, каждый
   перезапрос дёргал бы весь список на два пикселя вниз. */
.task-list__progress {
  position: absolute;
  top: -6px;
  z-index: 1;
}

/* Группа без задач — цель для переноса, а не содержимое: её видно, но спорить за внимание с
   группами, в которых есть работа, она не должна. Приглушение снимается под курсором: указатель
   над карточкой — уже намерение, и в этот момент она перестаёт быть фоном. Гасится прозрачностью
   целиком, а не цветом по частям: так ни один элемент шапки не выпадает из общего тона. */
.task-group--empty {
  opacity: 0.5;
  transition: opacity 120ms ease;
}

.task-group--empty:hover {
  opacity: 1;
}

/* Отступы шапки ужаты против ванильных: `VCardItem` рассчитан на карточку-страницу, а здесь он
   стоит над плотным списком в 36px на строку. */
.task-group__head {
  padding: 10px 12px;
}

/* «Без группы» — не цвет, а его отсутствие: нейтральная точка вместо знака, иначе остаток выглядел
   бы такой же названной группой, как соседние. Коробка та же, что у знака, — шапки соседних
   карточек стоят по одной линии. */
.task-group__dot {
  width: 28px;
  flex: none;
  position: relative;
}

.task-group__dot::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 6px;
  height: 6px;
  margin: -3px 0 0 -3px;
  border-radius: 50%;
  background: var(--text-faint);
}

/* Кегль и вес — свои: ванильный `VCardTitle` набран под заголовок карточки-страницы, а это
   имя группы над списком. Счёт стоит в той же строке, поэтому строка — flex. */
.task-group__title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 18px;
  color: var(--text);
}

.task-group__count {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: 11px;
  color: var(--text-faint);
}

/* Описание группы — одна строка под именем и тише его: это подпись к карточке, а не текст, который
   читают. Длинное обрезается, а не переносится: шапки групп должны быть одной высоты. */
.task-group__head :deep(.v-card-subtitle) {
  padding: 0;
  margin-top: 2px;
  font-size: 12px;
  line-height: 16px;
  color: var(--text-muted);
  opacity: 1;
}

.task-list__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 32px 16px;
  text-align: center;
}

.task-list__state-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.task-list__state-hint {
  margin: 0 0 6px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
