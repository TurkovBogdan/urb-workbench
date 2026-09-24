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
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  IconArrowDown,
  IconArrowUp,
  IconDotsVertical,
  IconListCheck,
  IconPencil,
  IconPlus,
} from '@tabler/icons-vue'

import CounterButton from '@/components/CounterButton.vue'
import IconSwatch from '@/components/IconSwatch.vue'
import TablePaginationBar from '@/components/TablePaginationBar.vue'

import GroupDropZone from './GroupDropZone.vue'
import TaskRows from './TaskRows.vue'
import { useTasksStore, type TaskSection } from '../stores/tasks.store'
import type { GroupRow, TaskListRow } from '../api'

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
  /** Правка группы: окно формы одно на страницу, и держит его она, а не список. */
  editGroup: [group: GroupRow]
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

// ── Свёрнутость ───────────────────────────────────────────────────────────────
// Умолчание зависит от того, есть ли в карточке работа: пустая приходит свёрнутой — она стоит на
// экране как цель перетаскивания, а не как содержимое. Явный выбор человека сильнее умолчания, и
// хранит его стор; здесь только передаём ему, какое умолчание действует для этой секции.

function collapsed(section: TaskSection): boolean {
  return store.isCollapsed(section.group?.code ?? null, !section.tasks.length)
}

function toggleFold(section: TaskSection) {
  store.toggleCollapsed(section.group?.code ?? null, !section.tasks.length)
}

/**
 * Порядок меняют только на ПОЛНОЙ выдаче.
 *
 * Сужённый список — это выборка, а не раскладка: ветки в нём не рисуются, соседи по группе на
 * экране не все, и «поставить после видимого соседа» означало бы не то, что человек видит. Гаснет
 * всё разом — перетаскивание строк, их ручки и пункты перестановки в меню строк и карточек.
 */
const reorderable = computed(() => !store.hasActiveFilters)

// ── Перестановка групп ────────────────────────────────────────────────────────
// Только пунктами меню карточки, без жеста: ручка у каждой карточки и второй sortable на странице
// перегружали список ради действия, которое делают редко (решение в `TASK@717492e127`).
//
// «Выше» — встать над соседкой сверху, «Ниже» — под соседкой снизу. Считается по секциям на
// экране, мимо «Без группы»: её в раскладке групп не существует.
//
// Шаг не выходит за свой блок. Пустые карточки на экране стоят ниже непустых независимо от `sort`
// (см. `sections` в сторе), поэтому «Ниже» у последней заполненной группы записало бы новый
// порядок, ничего при этом не изменив на экране, — шаг, который выглядит сломанным. На границе
// блока пункт меню гаснет, и это честнее: там двигаться действительно некуда.

function blockOf(code: string): string[] {
  const own = store.sections.find((section) => section.group?.code === code)
  if (!own) return []
  const empty = !own.tasks.length
  return store.sections
    .filter((section) => !!section.group && !section.tasks.length === empty)
    .map((section) => section.group!.code)
}

function shiftTarget(code: string, direction: -1 | 1): string | undefined {
  const order = blockOf(code)
  const at = order.indexOf(code)
  if (at === -1) return undefined
  const target = at + direction
  if (target < 0 || target >= order.length) return undefined
  return order[target]
}

function canShift(code: string, direction: -1 | 1): boolean {
  return shiftTarget(code, direction) !== undefined
}

function shift(code: string, direction: -1 | 1) {
  const target = shiftTarget(code, direction)
  if (!target) return
  void store.reorderGroup(code, direction === -1 ? { before: target } : { after: target })
}

/**
 * Строку переставили — перестановку ведёт стор: он же перечитывает список после ответа.
 *
 * Группа и родитель едут дальше ТОЛЬКО если их назвали: ключ без значения означает «не трогать»,
 * и потерять это различие здесь значило бы снять группу при обычной перестановке.
 */
async function move(payload: {
  code: string
  after: string | null
  group?: string | null
  parent?: string | null
}) {
  await store.reorder(payload.code, payload.after, {
    ...('group' in payload ? { group: payload.group } : {}),
    ...('parent' in payload ? { parent: payload.parent } : {}),
  })
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
          <!-- Выход из пустой выдачи должен что-то менять. Если фильтров не набрано и всё
               спрятало умолчание, «сбросить фильтры» вернуло бы ровно это же умолчание — здесь
               помогает только снять его. -->
          <VBtn v-if="store.hasActiveFilters" variant="text" size="small" @click="store.clearFilters">
            {{ t('tasks.task.list.clear_filters') }}
          </VBtn>
          <VBtn v-else variant="text" size="small" @click="store.showFinished">
            {{ t('tasks.task.list.show_finished') }}
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
           тема наравне с остальными, а остаток неразложенного.
           Шапка же — цель броска (`GroupDropZone`): у свёрнутой и у пустой карточки ряда строк
           нет, и задачу, брошенную на шапку, группа принимает в конец своего ряда. -->
      <GroupDropZone
        :group="section.group?.code ?? ''"
        :after="store.lastRootOf(section.group?.code ?? null)"
      >
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

        <!-- Сразу за именем — счёт задач и стрелка сворачивания, та же кнопка, что у строки задачи
             с подзадачами. Значок свой, а не «подзадачи» строки: иначе группа читалась бы задачей с
             подзадачами. Ноль показывается: у группы это ответ, а не отсутствие счёта. -->
        <VCardTitle class="task-group__title">
          {{ section.group ? section.group.title : t('tasks.task.list.no_group') }}
          <CounterButton
            class="task-group__fold"
            :icon="IconListCheck"
            :count="section.tasks.length"
            :folded="collapsed(section)"
            :label="t(collapsed(section) ? 'tasks.task.list.expand_group' : 'tasks.task.list.collapse_group')"
            @toggle="toggleFold(section)"
          />
        </VCardTitle>
        <VCardSubtitle v-if="section.group?.description">{{ section.group.description }}</VCardSubtitle>

        <!-- У «Без группы» меню нет: за ней не стоит строки в базе, править и двигать нечего. -->
        <template #append>
          <VMenu v-if="section.group" location="bottom end">
            <template #activator="{ props: menu }">
              <VBtn
                v-bind="menu"
                variant="text"
                size="x-small"
                icon
                class="task-group__more"
                :aria-label="t('tasks.group.card.actions')"
              >
                <IconDotsVertical :size="16" :stroke-width="1.7" />
              </VBtn>
            </template>

            <VList density="compact" class="task-group__menu">
              <VListItem :prepend-icon="IconPencil" @click="emit('editGroup', section.group)">
                <VListItemTitle>{{ t('tasks.group.card.edit') }}</VListItemTitle>
              </VListItem>

              <!-- Те же две перестановки без мыши: WCAG 2.2 SC 2.5.7 просит альтернативу жесту
                   одним указателем, а меню, открываемое с клавиатуры, закрывает и SC 2.1.1.
                   На сужённой выдаче их нет — как нет и самого жеста. -->
              <template v-if="reorderable">
                <VListItem
                  :prepend-icon="IconArrowUp"
                  :disabled="!canShift(section.group.code, -1)"
                  @click="shift(section.group.code, -1)"
                >
                  <VListItemTitle>{{ t('tasks.group.card.move_up') }}</VListItemTitle>
                </VListItem>
                <VListItem
                  :prepend-icon="IconArrowDown"
                  :disabled="!canShift(section.group.code, 1)"
                  @click="shift(section.group.code, 1)"
                >
                  <VListItemTitle>{{ t('tasks.group.card.move_down') }}</VListItemTitle>
                </VListItem>
              </template>
            </VList>
          </VMenu>
        </template>
      </VCardItem>
      </GroupDropZone>

      <template v-if="!collapsed(section)">
        <VDivider />

        <TaskRows
          :section="section"
          :open-code="props.openCode"
          :child-counts="childCounts"
          :reorderable="reorderable"
          @open="emit('open', $event)"
          @edit="emit('edit', $event)"
          @add-child="emit('addChild', $event)"
          @remove="store.remove($event)"
          @restore="store.restore($event)"
          @move="move"
        />
      </template>
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
   имя группы над списком. Кнопка ветки стоит в той же строке, поэтому строка — flex. */
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

/* Вид кнопки ветки — её собственный (`CounterButton`); шапка задаёт только место: отрицательный
   отступ прячет поле кнопки, и значок стоит от имени там же, где у строки задачи. Проявляет
   кнопку наведение на карточку — но переменная ставится на шапку, а не на всю карточку: иначе
   она протекла бы в строки задач, и под курсором проявились бы и их кнопки. */
.task-group__fold { margin-inline-start: -4px; }

.task-group:hover .task-group__head { --counter-button-color: var(--text-muted); }

/* Меню приглушено постоянно и проявляется под курсором: звать к себе ему незачем. */
.task-group__more {
  color: var(--text-faint);
  opacity: 0.7;
  transition: opacity 120ms ease, color 120ms ease;
}

.task-group:hover .task-group__more {
  opacity: 1;
  color: var(--text-muted);
}

.task-group__head :deep(.v-card-item__append) {
  display: flex;
  align-items: center;
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
